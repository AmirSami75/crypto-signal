using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Security;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Application.Trading.Risk;
using CryptoSignal.Api.Clients;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.Application.Trading.Execution;

/// <summary>
/// Runs one bot through one candle, start to finish, under the bot's advisory lock. This is the
/// orchestration the safety policy describes; every other trading type exists so that this method can be
/// read top to bottom and checked against the policy.
/// </summary>
/// <remarks>
/// <para>
/// The pipeline is fixed and ordered: kill-switch check → fetch candles → persist the window →
/// consult the engine → persist the decision → build the intent → risk-evaluate → place → record the
/// order and fills → update the position → append the audit chain. Nothing here is reordered for
/// convenience, because the order <em>is</em> the safety argument: risk runs before the broker, the
/// decision is durable before the intent, the window is stored before it is acted on.
/// </para>
/// <para>
/// Two faults halt the bot rather than being retried, because trading through either is how the platform
/// loses track of its own money: a market-data source that cannot produce the window (there is no
/// fallback venue by design), and an ambiguous order outcome (the venue may or may not hold the order).
/// Every other failure abandons the tick and leaves the bot to try the next candle.
/// </para>
/// <para>
/// It is scoped — one instance per tick — so the injected repositories and DbContext all share one
/// connection, which is what lets the advisory lock taken here cover every query the tick makes.
/// </para>
/// </remarks>
public sealed class BotTickExecutor(
    IRepo<TradingBot> bots,
    IRepo<MarketCandle> candles,
    IRepo<StrategyDecision> decisions,
    IRepo<ScannerSignal> scannerSignals,
    IRepo<OrderIntent> intents,
    IRepo<RiskDecision> riskDecisions,
    IRepo<ExchangeOrder> exchangeOrders,
    IRepo<OrderFill> fills,
    IRepo<BotPosition> positions,
    IAdvisoryLock advisoryLock,
    IKillSwitchGuard killSwitchGuard,
    IMarketDataSourceResolver marketData,
    IInstrumentRuleProvider instrumentRules,
    IMlServiceClient engine,
    IRiskEngine riskEngine,
    IBrokerResolver brokers,
    ICredentialProvider credentials,
    IBotAuditTrail audit,
    IOptions<TradingOptions> options,
    IOptions<TradingRiskOptions> riskLimits,
    ILogger<BotTickExecutor> logger) : IScopedSvcMarker
{
    // A conservative fee assumption folded into the estimated notional so the notional check and the
    // balance check both budget for the round trip. The venue's real fee is recorded from fills.
    private const decimal AssumedFeeBps = 10m;

    public async Task<TickOutcome> ExecuteAsync(Guid botId, CancellationToken cancellationToken)
    {
        var correlationId = Guid.CreateVersion7().ToString("N");

        var bot = await bots.Table.FirstOrDefaultAsync(b => b.Id == botId, cancellationToken);
        if (bot is null)
            return new TickOutcome(TickResult.Skipped, correlationId, Message: "bot not found");

        if (bot.Status != BotStatus.Active)
            return new TickOutcome(TickResult.Skipped, correlationId, Message: $"bot is {bot.Status}");

        // The advisory lock is the real mutual exclusion between replicas. A refusal means another worker
        // already holds this bot — a normal outcome, not a failure.
        await using var lockHandle =
            await advisoryLock.TryAcquireAsync(TradingIdentifiers.AdvisoryLockKey(botId), cancellationToken);

        if (lockHandle is null)
            return new TickOutcome(TickResult.Skipped, correlationId, Message: "another worker holds the bot");

        try
        {
            // Settle before anything else and before any "already evaluated this candle" shortcut: a tick
            // that died between the venue's fill and the position update leaves a position marked open on a
            // book that is already flat, and every later decision is derived from that book.
            await SettleStrandedIntentsAsync(bot, correlationId, cancellationToken);

            return await RunPipelineAsync(bot, correlationId, cancellationToken);
        }
        catch (BotFaultException fault)
        {
            await FaultBotAsync(bot, correlationId, fault.Message, cancellationToken);
            return new TickOutcome(TickResult.Faulted, correlationId, Message: fault.Message);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception exception)
        {
            // An unexpected failure abandons the tick but does not fault the bot — the next candle gets a
            // clean attempt. Only the two named, must-not-trade-through faults halt it.
            logger.LogError(exception, "Bot {BotId} tick failed (correlation {CorrelationId})", botId, correlationId);
            return new TickOutcome(TickResult.Skipped, correlationId, Message: exception.Message);
        }
    }

    private async Task<TickOutcome> RunPipelineAsync(
        TradingBot bot,
        string correlationId,
        CancellationToken cancellationToken)
    {
        // ── 1. kill-switch early exit ────────────────────────────────────────────
        var blocking = await killSwitchGuard.GetBlockingAsync(bot, cancellationToken);
        if (blocking.Count > 0)
        {
            var scopes = string.Join("; ", blocking.Select(k => $"{k.Scope}: {k.Reason}"));
            await audit.AppendAsync(
                new BotAuditEntry(
                    correlationId, BotAuditEventType.KillSwitchBlocked, bot.OperatingMode,
                    $"Blocked by kill switch(es): {scopes}",
                    BotId: bot.Id, Symbol: bot.Symbol,
                    KillSwitchId: blocking[0].Id,
                    Detail: new { scopes = blocking.Select(k => k.Scope.ToString()) }),
                cancellationToken);

            return new TickOutcome(TickResult.Blocked, correlationId, Message: scopes);
        }

        // ── 2. fetch candles (no fallback; a missing window faults the bot) ───────
        // One retry inside the tick: a transient TLS blip through the outbound proxy must not
        // permanently halt a bot, but there is still no second venue and no skip — after the
        // retry the failure faults exactly as before. Fail-closed, just not fail-once.
        var source = marketData.Resolve(bot.Venue);
        // A wildcard Scanner bot has no market of its own — it names the market per claimed proposal.
        // The tick still needs a clock and a freshness reference, so it reads BTCUSDT's window and the
        // claimed symbol's own price is fetched after the claim.
        var windowSymbol = bot.Kind == BotKind.Scanner && bot.Symbol == "*" ? "BTCUSDT" : bot.Symbol;
        IReadOnlyList<MarketCandleData> window;
        try
        {
            try
            {
                window = await source.GetClosedCandlesAsync(
                    windowSymbol, bot.Interval, options.Value.CandleWindowSize, cancellationToken);
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                await Task.Delay(TimeSpan.FromSeconds(3), cancellationToken);
                logger.LogWarning(
                    "Bot {BotId} candle fetch retry after: {Message}", bot.Id, exception.Message);
                window = await source.GetClosedCandlesAsync(
                    windowSymbol, bot.Interval, options.Value.CandleWindowSize, cancellationToken);
            }
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            throw new BotFaultException(
                $"the {bot.Venue} candle window for {windowSymbol} {bot.Interval} could not be fetched: " +
                $"{exception.Message}");
        }

        if (window.Count == 0)
            throw new BotFaultException($"the {bot.Venue} source returned no candles for {bot.Symbol}");

        var newest = window[^1];
        var candleOpenTime = newest.OpenTime.UtcDateTime;

        // ── freshness gate: refuse to think about a market we cannot see ─────────
        // The risk engine denies intents on stale candles, but by then the engine has already
        // been consulted and a decision recorded against data that may be hours old — and with no
        // open position there is nothing for the denial to protect. Fail here instead: the tick
        // faults, the audit trail says why, and consecutive-failure accounting treats it like any
        // other fault. A venue serving frozen klines must not produce decisions that look live.
        if (CandleInterval.TryToTimeSpan(bot.Interval, out var intervalSpan))
        {
            var candleAge = DateTime.UtcNow - newest.CloseTime.UtcDateTime;
            var maxAge = TimeSpan.FromTicks((long)(intervalSpan.Ticks * options.Value.MaxCandleAgeIntervals));
            if (candleAge > maxAge)
                throw new BotFaultException(
                    $"the newest closed {bot.Interval} candle for {bot.Symbol} closed " +
                    $"{(int)candleAge.TotalMinutes} minutes ago, beyond the tolerated " +
                    $"{(int)maxAge.TotalMinutes} — the venue feed looks stalled");
        }

        // ── idempotency: has this candle already been decided on? ────────────────
        var sameCandle = bot.LastEvaluatedCandleOpenTime == candleOpenTime;
        // A model bot is finished with a candle once it has decided on it. A scanner bot is not:
        // proposals arrive during the candle and it must be able to claim one, so a repeat tick skips
        // only the re-recording, not the claim.
        if (sameCandle && bot.Kind != BotKind.Scanner)
            return new TickOutcome(TickResult.AlreadyEvaluated, correlationId, Message: "candle already evaluated");

        var alreadyDecided = await decisions.TableNoTracking
            .AnyAsync(d => d.BotId == bot.Id && d.CandleOpenTime == candleOpenTime, cancellationToken);
        if (alreadyDecided)
        {
            await MarkEvaluatedAsync(bot, candleOpenTime, cancellationToken);
            return new TickOutcome(TickResult.AlreadyEvaluated, correlationId, Message: "decision already exists");
        }

        // ── 3. persist the window (only the candles not already stored) ──────────
        if (!sameCandle)
        {
            await PersistWindowAsync(bot, window, cancellationToken);
            await audit.AppendAsync(
                new BotAuditEntry(
                    correlationId, BotAuditEventType.CandleWindowRecorded, bot.OperatingMode,
                    $"Recorded {window.Count} {bot.Interval} candles for {windowSymbol} up to {candleOpenTime:O}",
                    BotId: bot.Id, Symbol: windowSymbol, CandleOpenTime: candleOpenTime),
                cancellationToken);
            bot.LastEvaluatedCandleOpenTime = candleOpenTime;
            bot.LastTickAt = DateTime.UtcNow;
            await bots.UpdateAsync(bot, saveNow: true, cancellationToken);
        }

        // ── 4. produce a decision ─────────────────────────────────────────────────
        // Scanner-kind bots never consult the ML engine: their signal comes from the market
        // scanner's strategy league, claimed atomically from the proposal table. Model bots
        // (the default) continue into the engine consult below.
        var openPosition = await LoadOpenPositionAsync(bot, cancellationToken);

        if (bot.Kind == BotKind.Scanner)
        {
            var scannerOutcome = await RunScannerBotAsync(
                bot, window, candleOpenTime, openPosition, correlationId, cancellationToken);
            if (scannerOutcome is not null)
                return scannerOutcome;

            // No unclaimed signal this tick: a complete, recorded no-op that still advances the tick
            // clock, so the scheduler honours the bot's cadence instead of re-running every poll.
            bot.LastTickAt = DateTime.UtcNow;
            await bots.UpdateAsync(bot, saveNow: true, cancellationToken);
            return new TickOutcome(TickResult.Hold, correlationId, Message: "no unclaimed scanner signal");
        }

        // Fetch higher-TF context candles when the bot is configured for MTF.
        // The engine uses them as confluence features; a missing context source
        // is treated like a missing main candle window — a transient retry, then fault.
        IReadOnlyList<MlCandle>? contextCandles = null;
        var mtfContextInterval = options.Value.MtfContextInterval;
        if (!string.IsNullOrWhiteSpace(mtfContextInterval))
        {
            try
            {
                try
                {
                    var contextWindow = await source.GetClosedCandlesAsync(
                        bot.Symbol, mtfContextInterval, options.Value.MtfContextCandles,
                        cancellationToken);
                    contextCandles = contextWindow.Select(ToMlCandle).ToList();
                }
                catch (Exception exception) when (exception is not OperationCanceledException)
                {
                    await Task.Delay(TimeSpan.FromSeconds(3), cancellationToken);
                    logger.LogWarning(
                        "Bot {BotId} MTF context fetch retry after: {Message}",
                        bot.Id, exception.Message);
                    var contextWindow = await source.GetClosedCandlesAsync(
                        bot.Symbol, mtfContextInterval, options.Value.MtfContextCandles,
                        cancellationToken);
                    contextCandles = contextWindow.Select(ToMlCandle).ToList();
                }
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                throw new BotFaultException(
                    $"the {bot.Venue} MTF context window for {bot.Symbol} {mtfContextInterval} could not be fetched: " +
                    $"{exception.Message}");
            }
        }

        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.EngineConsulted, bot.OperatingMode,
                $"Asking the engine for a decision on {bot.Symbol} {bot.Interval}",
                BotId: bot.Id, Symbol: bot.Symbol, CandleOpenTime: candleOpenTime),
            cancellationToken);

        var decisionResponse = await engine.EvaluateBotDecisionAsync(
            new MlBotDecisionRequest(
                BotId: bot.Id.ToString(),
                Symbol: bot.Symbol,
                Interval: bot.Interval,
                Candles: window.Select(ToMlCandle).ToList(),
                Parameters: new MlTradeParameters(
                    bot.TakeProfitPercent,
                    bot.StopLossPercent,
                    bot.AllowShort,
                    (uint)Math.Max(0, bot.MaxHoldingPeriods),
                    bot.MinimumConfidence,
                    (double)(bot.TakeProfitAtrMultiple ?? 0m),
                    (double)(bot.StopLossAtrMultiple ?? 0m)),
                Position: openPosition is null ? null : ToMlPosition(openPosition),
                ExpectedModelVersion: bot.ExpectedModelVersion,
                RequestId: correlationId,
                ContextCandles: contextCandles,
                ContextInterval: mtfContextInterval),
            cancellationToken);

        // ── 5. persist the decision (durable before any intent) ──────────────────
        // An unset action is read as HOLD. BotDecisionAction has no zero member precisely so that a
        // missing instruction cannot be stored as though the engine had said something.
        var action = decisionResponse.Action is MlBotAction.Unspecified
            ? BotDecisionAction.Hold
            : (BotDecisionAction)(int)decisionResponse.Action;

        var decision =
            await PersistDecisionAsync(bot, decisionResponse, action, candleOpenTime, cancellationToken);
        await MarkEvaluatedAsync(bot, candleOpenTime, cancellationToken);
        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.StrategyDecisionRecorded, bot.OperatingMode,
                $"Engine advised {decisionResponse.Action} {decisionResponse.Direction} " +
                $"(confidence {decisionResponse.Confidence:F4}, reason {decisionResponse.ReasonCode})",
                BotId: bot.Id, Symbol: bot.Symbol, CandleOpenTime: candleOpenTime,
                StrategyDecisionId: decision.Id, ModelVersion: decision.ModelVersion,
                Detail: new { decisionResponse.ReasonCode, decisionResponse.Confidence, decisionResponse.ExpectedValue }),
            cancellationToken);

        // A HOLD is a complete, recorded outcome: the platform looked and chose not to act.
        if (action is BotDecisionAction.Hold)
            return new TickOutcome(TickResult.Hold, correlationId, decision.Id, Action: action);

        // Moving a bracket on an existing paper position is bookkeeping, not a new order: no exposure is
        // opened, so it does not pass through the broker.
        if (action is BotDecisionAction.AdjustBracket)
        {
            await AdjustBracketAsync(bot, openPosition, decisionResponse, correlationId, cancellationToken);
            return new TickOutcome(TickResult.Hold, correlationId, decision.Id, Action: action);
        }

        // ── 6. build the intent, ── 7. risk, ── 8. place (shared with scanner bots) ──
        return await ActOnDecisionAsync(
            bot, decision, action, openPosition, window, correlationId,
            candleOpenTime, cancellationToken);
    }

    /// <summary>
    /// The scanner-kind bot's step 4: claim the newest unclaimed scanner signal matching this bot's
    /// market and strategy, and turn it into an OPEN decision that walks the ordinary pipeline.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The claim is a single conditional UPDATE (<c>SET TakenByBotId WHERE TakenByBotId IS NULL</c>),
    /// so two scanner bots racing the same signal produce exactly one winner; the loser sees zero rows
    /// affected and stands down for this tick. The claim happens <em>before</em> the decision is
    /// written, so a bot that faults after claiming does not leave the signal for another bot — a
    /// lost proposal is safer than a duplicated order.
    /// </para>
    /// <para>
    /// The decision this method synthesizes is deliberately shaped like an engine answer: same table,
    /// same columns, <c>ModelId = "strategy-zoo"</c> and the strategy key as its version, so the audit
    /// chain and the risk engine need no special cases.
    /// </para>
    /// </remarks>
    private async Task<TickOutcome?> RunScannerBotAsync(
        TradingBot bot,
        IReadOnlyList<MarketCandleData> window,
        DateTime candleOpenTime,
        BotPosition? openPosition,
        string correlationId,
        CancellationToken cancellationToken)
    {
        // An open position is managed here, not by a second decision: a scanner bot never opens another
        // one while the first is live, but it must still exit — a bracket nobody watches is a position
        // that only closes when an operator clicks. The exit test runs on the last *closed* candle.
        if (openPosition is not null)
        {
            var exit = await EvaluateScannerExitAsync(
                bot, openPosition, candleOpenTime, correlationId, cancellationToken);
            if (exit is null)
                return new TickOutcome(TickResult.Hold, correlationId, Message: "position open; no exit level touched");

            var (exitDecision, exitAction) = exit.Value;
            return await ActOnDecisionAsync(
                bot, exitDecision, exitAction, openPosition, window, correlationId,
                candleOpenTime, cancellationToken);
        }

        // Oldest-first was right when every proposal was an indicator firing; with a model that prices
        // expected R, the bot should take the *best* opportunity, not the stalest one. A stale proposal
        // is also dangerous: its levels were computed from candles that no longer describe the market.
        var settings = options.Value;
        var cutoff = DateTime.UtcNow.AddMinutes(-Math.Max(1, settings.ScannerMaxSignalAgeMinutes));
        // A wildcard scanner must only claim markets the risk layer would actually allow, otherwise it
        // burns the best proposal of the pass on a symbol the risk engine denies one step later.
        var allowedSymbols = riskLimits.Value.AllowedSymbols
            .Select(s => s.ToUpperInvariant())
            .ToArray();
        var candidate = await scannerSignals.TableNoTracking
            .Where(s => s.TakenByBotId == null
                        && s.Interval == bot.Interval
                        && s.CreatedAt >= cutoff
                        && s.Score >= settings.ScannerMinimumScore
                        && (bot.Symbol != "*"
                            ? s.Symbol == bot.Symbol
                            : allowedSymbols.Contains(s.Symbol)))
            // An unpinned scanner bot consumes model proposals. Zoo rows only exist when the scanner's
            // model pass is disabled, and their score is a liquidity heuristic — mixing it with expected
            // R in one ranking column would let a heuristic outrank the model.
            .Where(s => bot.StrategyKey != null ? s.StrategyKey == bot.StrategyKey : s.StrategyKey == "model")
            .OrderByDescending(s => s.Score)
            .ThenByDescending(s => s.CreatedAt)
            .FirstOrDefaultAsync(cancellationToken);

        if (candidate is null)
            return null;

        // The proposal may be for a market this bot holds no window for (wildcard scanner), so the entry
        // price is read from the proposal's own market before anything is claimed: a claim that cannot
        // be priced would burn the opportunity for every other bot.
        decimal entryPrice;
        try
        {
            var entryWindow = await marketData.Resolve(bot.Venue)
                .GetClosedCandlesAsync(candidate.Symbol, bot.Interval, 2, cancellationToken);
            entryPrice = entryWindow[^1].Close;
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return new TickOutcome(TickResult.Hold, correlationId,
                Message: $"scanner signal {candidate.Id} entry price unavailable: {exception.Message}");
        }

        // Shorts are a bet the bot must be configured to take, same rule as the engine advisor.
        var direction = candidate.Direction == SignalDirection.Long
            ? TradeDirection.Long
            : TradeDirection.Short;
        if (direction == TradeDirection.Short && !bot.AllowShort)
            return new TickOutcome(TickResult.Hold, correlationId,
                Message: $"scanner signal {candidate.Id} is SHORT but the bot does not allow shorts");

        // ── atomic claim: exactly one bot wins this UPDATE ────────────────────────
        var claimed = await scannerSignals.Table
            .Where(s => s.Id == candidate.Id && s.TakenByBotId == null)
            .ExecuteUpdateAsync(
                update => update.SetProperty(s => s.TakenByBotId, bot.Id),
                cancellationToken);

        if (claimed == 0)
            return new TickOutcome(TickResult.Hold, correlationId,
                Message: "scanner signal claimed by another bot");

        var atr = candidate.AtrAtSignal;

        // Bracket: the bot's ATR multiples when set, else the scanner defaults (1.5 / 1.0 ATR),
        // expressed off the signal's ATR. Percent fields are the fallback when no ATR is known.
        var tpAtrMultiple = bot.TakeProfitAtrMultiple ?? 1.5m;
        var slAtrMultiple = bot.StopLossAtrMultiple ?? 1.0m;
        decimal takeProfit, stopLoss;
        if (atr > 0)
        {
            takeProfit = direction == TradeDirection.Long
                ? entryPrice + tpAtrMultiple * atr
                : entryPrice - tpAtrMultiple * atr;
            stopLoss = direction == TradeDirection.Long
                ? entryPrice - slAtrMultiple * atr
                : entryPrice + slAtrMultiple * atr;
        }
        else
        {
            takeProfit = direction == TradeDirection.Long
                ? entryPrice * (1 + bot.TakeProfitPercent / 100m)
                : entryPrice * (1 - bot.TakeProfitPercent / 100m);
            stopLoss = direction == TradeDirection.Long
                ? entryPrice * (1 - bot.StopLossPercent / 100m)
                : entryPrice * (1 + bot.StopLossPercent / 100m);
        }

        var decision = new StrategyDecision
        {
            BotId = bot.Id,
            OperatingMode = bot.OperatingMode,
            Symbol = candidate.Symbol,
            Interval = candidate.Interval,
            CandleOpenTime = candleOpenTime,
            CandleWindowDigest = string.Empty,
            Action = BotDecisionAction.Open,
            Direction = direction,
            ReasonCode = "scanner_signal",
            Confidence = candidate.Confidence,
            LongConfidence = direction == TradeDirection.Long ? candidate.Confidence : 0,
            ShortConfidence = direction == TradeDirection.Short ? candidate.Confidence : 0,
            // For a scanner bot this column carries the proposal's ranking number — expected R when the
            // served bundle has a points head. It is not ATR units like the model bots' expected value,
            // and the scanner-sourced ReasonCode is what tells the two apart in the audit trail.
            ExpectedValue = (double)candidate.Score,
            EntryPrice = entryPrice,
            TakeProfitPrice = takeProfit,
            StopLossPrice = stopLoss,
            Atr = atr > 0 ? atr : null,
            ModelId = "strategy-zoo",
            ModelVersion = candidate.StrategyKey,
            UsedWildcardModel = false,
            BarrierExtrapolated = false,
            EngineRequestId = correlationId,
            Warning = $"scanner proposal {candidate.Id} ({candidate.StrategyKey}): {candidate.Reason}",
        };
        await decisions.AddAsync(decision, saveNow: true, cancellationToken);
        await MarkEvaluatedAsync(bot, candleOpenTime, cancellationToken);

        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.ScannerSignalClaimed, bot.OperatingMode,
                $"Claimed scanner signal {candidate.Id} ({candidate.StrategyKey} {candidate.Direction}) " +
                $"for {candidate.Symbol} @ ~{entryPrice}",
                BotId: bot.Id, Symbol: bot.Symbol,
                StrategyDecisionId: decision.Id, CandleOpenTime: candleOpenTime,
                Detail: new { signalId = candidate.Id, candidate.StrategyKey, candidate.Score }),
            cancellationToken);

        // From here the scanner bot walks the exact same intent → risk → place path as a model bot.
        return await ActOnDecisionAsync(
            bot, decision, BotDecisionAction.Open, openPosition, window, correlationId,
            candleOpenTime, cancellationToken);
    }

    /// <summary>
    /// The exit test for an open scanner position: does the last closed candle touch a bracket level?
    /// </summary>
    /// <remarks>
    /// Both levels can be touched inside one candle — the candle carries a high and a low, not an order
    /// of events. When that happens the stop wins: assuming the take-profit filled first would book the
    /// best possible outcome of an ambiguous bar, which is exactly the optimism a backtest cannot afford.
    /// </remarks>
    private async Task<(StrategyDecision Decision, BotDecisionAction Action)?> EvaluateScannerExitAsync(
        TradingBot bot,
        BotPosition openPosition,
        DateTime candleOpenTime,
        string correlationId,
        CancellationToken cancellationToken)
    {
        if (openPosition.ClosedAt is not null || openPosition.Quantity <= 0)
            return null;
        if (string.IsNullOrWhiteSpace(openPosition.Symbol) || openPosition.Symbol == "*")
            return null; // a position booked before the wildcard fix cannot be priced; leave it to an operator

        var interval = bot.Interval.EndsWith('m')
            ? TimeSpan.FromMinutes(double.Parse(bot.Interval[..^1]))
            : TimeSpan.FromHours(double.Parse(bot.Interval[..^1]));
        var barsOpen = interval > TimeSpan.Zero
            ? Math.Max(0, (int)((candleOpenTime - openPosition.OpenedFromCandleOpenTime).TotalSeconds / interval.TotalSeconds))
            : 0;

        // Every candle the position has lived through, not just the newest one. A restart used to make
        // the exit blind: a stop touched while the process was down was never tested again, so the
        // position sat open at a price the bracket had already abandoned.
        var wanted = (int)Math.Clamp(barsOpen + 2, 2, 300);

        IReadOnlyList<MarketCandleData> candles;
        try
        {
            candles = await marketData.Resolve(bot.Venue)
                .GetClosedCandlesAsync(openPosition.Symbol, bot.Interval, wanted, cancellationToken);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            logger.LogWarning(exception, "Scanner exit for {Symbol} could not read candles", openPosition.Symbol);
            return null;
        }

        if (candles.Count == 0)
            return null;

        var isLong = openPosition.Direction == TradeDirection.Long;
        var takeProfit = openPosition.TakeProfitPrice;
        var stopLoss = openPosition.StopLossPrice;

        string? reason = null;
        decimal exitPrice = 0m;
        DateTime exitCandleOpen = candles[^1].OpenTime.UtcDateTime;   // the candle that triggered, for the message

        // Oldest first: the first candle that violates the bracket is the one that ended the trade.
        foreach (var candle in candles)
        {
            if (stopLoss is { } stop && (isLong ? candle.Low <= stop : candle.High >= stop))
            {
                reason = "stop_loss_touched";
                exitPrice = stop;
                exitCandleOpen = candle.OpenTime.UtcDateTime;
                break;
            }

            if (takeProfit is { } take && (isLong ? candle.High >= take : candle.Low <= take))
            {
                reason = "take_profit_touched";
                exitPrice = take;
                exitCandleOpen = candle.OpenTime.UtcDateTime;
                break;
            }
        }

        if (reason is null && bot.MaxHoldingPeriods > 0 && barsOpen >= bot.MaxHoldingPeriods)
        {
            reason = "max_holding_periods_reached";
            exitPrice = candles[^1].Close;
        }

        if (reason is null)
            return null;

        // The decision is booked on *this tick's* candle, not on the candle that touched the level: the
        // idempotency key is (BotId, CandleOpenTime), and an exit discovered from a candle hours ago
        // already has a decision row — inserting a second one failed the whole scheduler cycle.
        var alreadyDecided = await decisions.TableNoTracking.AnyAsync(
            d => d.BotId == bot.Id && d.CandleOpenTime == candleOpenTime, cancellationToken);
        if (alreadyDecided)
            return null;

        var decision = new StrategyDecision
        {
            BotId = bot.Id,
            OperatingMode = bot.OperatingMode,
            Symbol = openPosition.Symbol,
            Interval = bot.Interval,
            CandleOpenTime = candleOpenTime,
            CandleWindowDigest = string.Empty,
            Action = BotDecisionAction.Close,
            Direction = openPosition.Direction,
            ReasonCode = reason,
            Confidence = 1d,
            LongConfidence = isLong ? 1d : 0d,
            ShortConfidence = isLong ? 0d : 1d,
            ExpectedValue = 0d,
            EntryPrice = exitPrice,
            TakeProfitPrice = takeProfit,
            StopLossPrice = stopLoss,
            Atr = null,
            ModelId = "scanner-exit",
            ModelVersion = reason,
            UsedWildcardModel = false,
            BarrierExtrapolated = false,
            EngineRequestId = correlationId,
            Warning = $"scanner exit on {openPosition.Symbol} ({reason}) at ~{exitPrice}; " +
                      $"first touched on the {exitCandleOpen:O} candle",
        };
        await decisions.AddAsync(decision, saveNow: true, cancellationToken);

        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.PositionChanged, bot.OperatingMode,
                $"Exit {openPosition.Symbol} ({reason}) at ~{exitPrice}",
                BotId: bot.Id, Symbol: openPosition.Symbol,
                StrategyDecisionId: decision.Id, CandleOpenTime: decision.CandleOpenTime),
            cancellationToken);

        return (decision, BotDecisionAction.Close);
    }

    /// <summary>
    /// Steps 6–8 shared by both bot kinds: build the intent, pass risk, place and record.
    /// Extracted verbatim from the model path so the safety argument is one pipeline, not two.
    /// </summary>
    private async Task<TickOutcome> ActOnDecisionAsync(
        TradingBot bot,
        StrategyDecision decision,
        BotDecisionAction action,
        BotPosition? openPosition,
        IReadOnlyList<MarketCandleData> window,
        string correlationId,
        DateTime candleOpenTime,
        CancellationToken cancellationToken)
    {
        // ── 6. build the intent (deterministic client order id) ──────────────────
        // Rules belong to the market being traded. A wildcard bot's registration symbol is `*`, and
        // asking the venue about `*` resolves another instrument's grid — which then prices the fill and
        // caps the quantity against the wrong market (a 0.2341 entry quantised to a 0.10 tick became
        // 0.30, and a 156-unit order was refused a 120-unit cap that belonged to BTCUSDT).
        var tradedSymbol = string.IsNullOrWhiteSpace(decision.Symbol) ? bot.Symbol : decision.Symbol;
        var rules = await instrumentRules.GetRulesAsync(bot.Venue, tradedSymbol, cancellationToken);
        var intent = BuildIntent(bot, decision, action, openPosition, rules);
        if (intent is null)
        {
            // The decision said OPEN/CLOSE but the levels or position needed to construct an order are
            // absent. Recorded via the decision; nothing is placed.
            return new TickOutcome(TickResult.Hold, correlationId, decision.Id, Action: action,
                Message: "no order could be constructed from the decision");
        }

        await intents.AddAsync(intent, saveNow: true, cancellationToken);
        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.OrderIntentCreated, bot.OperatingMode,
                $"Intent {intent.ClientOrderId}: {intent.Side} {intent.Quantity} {intent.Symbol} @ ~{intent.ReferencePrice}",
                BotId: bot.Id, Symbol: intent.Symbol, StrategyDecisionId: decision.Id,
                OrderIntentId: intent.Id, CandleOpenTime: candleOpenTime),
            cancellationToken);

        // ── 7. risk (the one gate; nothing reaches a broker without it) ──────────
        var broker = brokers.Resolve(bot.OperatingMode, bot.Venue);

        // Credentials come from the bot's pinned connection when it names one, else the owner's
        // active stored connection, else the environment. Resolved per tick so a deactivated
        // connection stops feeding orders on its very next evaluation.
        var creds = await ResolveCredentialsAsync(bot, cancellationToken);
        var balance = await broker.GetAvailableBalanceAsync(rules.QuoteAsset, creds, cancellationToken);

        var verdict = await riskEngine.EvaluateAsync(
            new RiskEvaluationContext(bot, decision, intent, rules, candleOpenTime, balance),
            cancellationToken);

        await PersistRiskDecisionAsync(bot, intent, verdict, cancellationToken);

        if (!verdict.Allowed)
        {
            intent.Status = OrderIntentStatus.RiskDenied;
            intent.StatusReason = verdict.Detail;
            intent.CompletedAt = DateTime.UtcNow;
            await intents.UpdateAsync(intent, saveNow: true, cancellationToken);

            await audit.AppendAsync(
                new BotAuditEntry(
                    correlationId, BotAuditEventType.RiskDenied, bot.OperatingMode,
                    $"Risk denied {intent.ClientOrderId} on: {verdict.FailedChecksCsv}",
                    BotId: bot.Id, Symbol: bot.Symbol, StrategyDecisionId: decision.Id,
                    OrderIntentId: intent.Id, CandleOpenTime: candleOpenTime,
                    Detail: new { verdict.FailedChecksCsv, verdict.Detail }),
                cancellationToken);

            return new TickOutcome(TickResult.RiskDenied, correlationId, decision.Id, intent.Id, action,
                verdict.FailedChecks, verdict.Detail);
        }

        intent.Status = OrderIntentStatus.Approved;
        await intents.UpdateAsync(intent, saveNow: true, cancellationToken);
        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.RiskAllowed, bot.OperatingMode,
                $"Risk allowed {intent.ClientOrderId}",
                BotId: bot.Id, Symbol: bot.Symbol, StrategyDecisionId: decision.Id,
                OrderIntentId: intent.Id, CandleOpenTime: candleOpenTime),
            cancellationToken);

        // ── 8. place, record, and update the position ────────────────────────────
        return await PlaceAndRecordAsync(
            bot, decision, intent, broker, creds, rules, action, openPosition, correlationId,
            window, cancellationToken);
    }

    /// <summary>
    /// Credentials for this tick: the bot's pinned connection if it names one (and it must belong to
    /// the bot's owner and be active), else the owner's most recent active connection for the venue,
    /// else null — which lets each broker apply its own environment fallback or fail closed.
    /// </summary>
    private async Task<VenueCredentials?> ResolveCredentialsAsync(
        TradingBot bot, CancellationToken cancellationToken)
    {
        try
        {
            if (bot.ExchangeConnectionId is { } pinned)
            {
                return bot.UserCreatedId is { } ownerId
                    ? await credentials.ForConnectionAsync(ownerId, pinned, cancellationToken)
                    : null;
            }

            return bot.UserCreatedId is { } owner
                ? await credentials.ResolveAsync(owner, bot.Venue, cancellationToken)
                : null;
        }
        catch (UnauthorizedAccessException exception)
        {
            logger.LogError(exception, "Bot {BotId} is pinned to an exchange connection it does not own",
                bot.Id);
            return null;
        }
    }

    // ── placement + position accounting ──────────────────────────────────────────

    private async Task<TickOutcome> PlaceAndRecordAsync(
        TradingBot bot,
        StrategyDecision decision,
        OrderIntent intent,
        IBroker broker,
        VenueCredentials? creds,
        InstrumentRules rules,
        BotDecisionAction action,
        BotPosition? openPosition,
        string correlationId,
        IReadOnlyList<MarketCandleData> window,
        CancellationToken cancellationToken)
    {
        intent.Status = OrderIntentStatus.Submitted;
        intent.SubmittedAt = DateTime.UtcNow;
        await intents.UpdateAsync(intent, saveNow: true, cancellationToken);

        var placement = await broker.PlaceAsync(
            new BrokerOrderRequest(
                intent.ClientOrderId, intent.Symbol, bot.Venue, rules,
                intent.Direction, intent.Side, intent.Type,
                intent.Quantity, intent.ReferencePrice, intent.LimitPrice,
                intent.TakeProfitPrice, intent.StopLossPrice, intent.TimeInForce, bot.MaxSlippageBps, intent.Leverage),
            creds, cancellationToken);

        var exchangeOrder = new ExchangeOrder
        {
            OrderIntentId = intent.Id,
            BotId = bot.Id,
            OperatingMode = bot.OperatingMode,
            Venue = bot.Venue,
            VenueOrderId = placement.VenueOrderId,
            ClientOrderId = intent.ClientOrderId,
            Status = placement.Status,
            FilledQuantity = placement.FilledQuantity,
            AverageFillPrice = placement.AverageFillPrice,
            RequestHash = placement.RequestHash,
            ResponseHash = placement.ResponseHash,
            SubmittedAt = intent.SubmittedAt.Value,
            VenueUpdatedAt = placement.VenueUpdatedAt?.UtcDateTime,
        };
        await exchangeOrders.AddAsync(exchangeOrder, saveNow: true, cancellationToken);
        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.OrderSubmitted, bot.OperatingMode,
                $"Submitted {intent.ClientOrderId}; venue said {placement.Outcome}/{placement.Status}",
                BotId: bot.Id, Symbol: bot.Symbol, OrderIntentId: intent.Id,
                ExchangeOrderId: exchangeOrder.Id,
                Detail: new { placement.Outcome, status = placement.Status.ToString(), placement.Detail }),
            cancellationToken);

        // An ambiguous write is the second must-not-trade-through fault: the venue may or may not hold the
        // order, and the only safe next move is to stop and reconcile, never to place anything else.
        if (placement.Outcome == BrokerOutcome.Ambiguous)
        {
            intent.Status = OrderIntentStatus.Ambiguous;
            intent.StatusReason = placement.Detail;
            await intents.UpdateAsync(intent, saveNow: true, cancellationToken);
            throw new BotFaultException(
                $"order {intent.ClientOrderId} returned an ambiguous outcome and must be reconciled: {placement.Detail}");
        }

        if (placement.Outcome == BrokerOutcome.Rejected)
        {
            intent.Status = OrderIntentStatus.Rejected;
            intent.StatusReason = placement.Detail;
            intent.CompletedAt = DateTime.UtcNow;
            await intents.UpdateAsync(intent, saveNow: true, cancellationToken);
            return new TickOutcome(TickResult.Skipped, correlationId, decision.Id, intent.Id, action,
                Message: $"venue rejected the order: {placement.Detail}");
        }

        // Record fills. The unique (Venue, VenueTradeId) index makes this idempotent — a reconciliation
        // that re-reports a fill cannot double-count it.
        var recordedFills = await RecordFillsAsync(bot, exchangeOrder, placement, cancellationToken);
        foreach (var fill in recordedFills)
        {
            await audit.AppendAsync(
                new BotAuditEntry(
                    correlationId, BotAuditEventType.FillRecorded, bot.OperatingMode,
                    $"Filled {fill.Quantity} @ {fill.Price} (fee {fill.Fee} {fill.FeeAsset})",
                    BotId: bot.Id, Symbol: bot.Symbol, OrderIntentId: intent.Id,
                    ExchangeOrderId: exchangeOrder.Id, OrderFillId: fill.Id),
                cancellationToken);
        }

        var position = await ApplyToPositionAsync(
            bot, decision, intent, exchangeOrder, recordedFills, action, openPosition, cancellationToken);

        if (position is not null)
        {
            await audit.AppendAsync(
                new BotAuditEntry(
                    correlationId, BotAuditEventType.PositionChanged, bot.OperatingMode,
                    $"Position {position.Status}: {position.Direction} {position.Quantity} {bot.Symbol}" +
                    (position.Status == PositionStatus.Closed ? $", realised {position.RealizedPnl}" : ""),
                    BotId: bot.Id, Symbol: bot.Symbol, OrderIntentId: intent.Id,
                    BotPositionId: position.Id, CandleOpenTime: decision.CandleOpenTime),
                cancellationToken);

            // The position's lifecycle produced a labelled example for the engine's online learner.
            // Best-effort and off the trading path: a failed report is logged by the client and
            // forgotten, never retried at the cost of a tick.
            if (position.Status == PositionStatus.Closed)
            {
                await ReportTradeOutcomeAsync(
                    bot, decision, position, window, correlationId, CancellationToken.None);
            }
        }

        if (placement.Status is ExchangeOrderStatus.Filled)
        {
            intent.Status = OrderIntentStatus.Filled;
            intent.CompletedAt = DateTime.UtcNow;
        }
        else if (placement.Status is ExchangeOrderStatus.PartiallyFilled)
        {
            intent.Status = OrderIntentStatus.PartiallyFilled;
        }
        await intents.UpdateAsync(intent, saveNow: true, cancellationToken);

        return new TickOutcome(TickResult.Traded, correlationId, decision.Id, intent.Id, action);
    }

    private async Task<IReadOnlyList<OrderFill>> RecordFillsAsync(
        TradingBot bot,
        ExchangeOrder exchangeOrder,
        BrokerPlacement placement,
        CancellationToken cancellationToken)
    {
        var recorded = new List<OrderFill>();

        foreach (var fill in placement.Fills)
        {
            // Idempotent by (Venue, VenueTradeId): skip a fill already stored rather than duplicating it.
            var exists = await fills.TableNoTracking.AnyAsync(
                f => f.Venue == bot.Venue && f.VenueTradeId == fill.VenueTradeId, cancellationToken);
            if (exists)
                continue;

            var row = new OrderFill
            {
                ExchangeOrderId = exchangeOrder.Id,
                BotId = bot.Id,
                OperatingMode = bot.OperatingMode,
                Venue = bot.Venue,
                VenueTradeId = fill.VenueTradeId,
                Price = fill.Price,
                Quantity = fill.Quantity,
                Fee = fill.Fee,
                FeeAsset = fill.FeeAsset,
                IsMaker = fill.IsMaker,
                ExecutedAt = fill.ExecutedAt.UtcDateTime,
            };
            await fills.AddAsync(row, saveNow: true, cancellationToken);
            recorded.Add(row);
        }

        return recorded;
    }

    private async Task<BotPosition?> ApplyToPositionAsync(
        TradingBot bot,
        StrategyDecision decision,
        OrderIntent intent,
        ExchangeOrder exchangeOrder,
        IReadOnlyList<OrderFill> newFills,
        BotDecisionAction action,
        BotPosition? openPosition,
        CancellationToken cancellationToken)
    {
        if (newFills.Count == 0)
            return null;

        var filledQty = newFills.Sum(f => f.Quantity);
        var grossNotional = newFills.Sum(f => f.Price * f.Quantity);
        var feePaid = newFills.Sum(f => f.Fee);
        var avgPrice = filledQty > 0 ? grossNotional / filledQty : 0m;

        if (action == BotDecisionAction.Open)
        {
            var position = new BotPosition
            {
                BotId = bot.Id,
                OperatingMode = bot.OperatingMode,
                Venue = bot.Venue,
                // The market that was traded, not the bot's registration symbol: a wildcard scanner
                // carries `*`, and a position booked against `*` cannot be marked to market, matched by
                // a closing decision, or shown against the symbol it actually holds.
                Symbol = string.IsNullOrWhiteSpace(intent.Symbol) ? bot.Symbol : intent.Symbol,
                Direction = intent.Direction,
                Status = PositionStatus.Open,
                AverageEntryPrice = avgPrice,
                Quantity = filledQty,
                EntryNotional = grossNotional,
                TakeProfitPrice = intent.TakeProfitPrice,
                StopLossPrice = intent.StopLossPrice,
                OpenedByOrderIntentId = intent.Id,
                OpenedFromCandleOpenTime = decision.CandleOpenTime,
                OpenedAt = DateTime.UtcNow,
                BarsHeld = 0,
                RealizedPnl = 0m,
                FeesPaid = feePaid,
            };
            await positions.AddAsync(position, saveNow: true, cancellationToken);
            return position;
        }

        // Close: settle against the position the engine was told about.
        if (openPosition is null)
            return null;

        var direction = openPosition.Direction;
        var realized = direction == TradeDirection.Long
            ? (avgPrice - openPosition.AverageEntryPrice) * filledQty
            : (openPosition.AverageEntryPrice - avgPrice) * filledQty;

        openPosition.Status = PositionStatus.Closed;
        openPosition.AverageExitPrice = avgPrice;
        openPosition.ClosedByOrderIntentId = intent.Id;
        openPosition.ClosedAt = DateTime.UtcNow;
        openPosition.RealizedPnl = realized - openPosition.FeesPaid - feePaid;
        openPosition.FeesPaid += feePaid;
        // The quantity stays at the size that was closed. Zeroing it read as "flat", but the row's own
        // check constraint requires a positive quantity on every row — so every close violated it and the
        // position could never settle. Status is what says the position is closed, not a zeroed size.
        openPosition.CloseReason = MapCloseReason(decision.ReasonCode);
        await positions.UpdateAsync(openPosition, saveNow: true, cancellationToken);
        return openPosition;
    }

    /// <summary>
    /// Reports one closed position to the engine's online learner: the exact candle window the opening
    /// decision consumed, the bracket actually traded, and how the position ended. Fire-and-forget by
    /// design — a lost sample costs one training datum, never a trade.
    /// </summary>
    /// <summary>
    /// A bracket level as a percentage of the entry, falling back to the bot's configured percentage when
    /// the position carries no level (a manual close, or a venue-side bracket the platform never saw).
    /// </summary>
    private static decimal BracketPercent(decimal entry, decimal? level, decimal fallback) =>
        entry > 0m && level is { } value && value > 0m
            ? Math.Abs((value - entry) / entry) * 100m
            : fallback;

    private async Task ReportTradeOutcomeAsync(
        TradingBot bot,
        StrategyDecision decision,
        BotPosition position,
        IReadOnlyList<MarketCandleData> window,
        string correlationId,
        CancellationToken cancellationToken)
    {
        if (position.ClosedAt is null)
            return;

        // The engine learns from the window the decision consumed. For a wildcard bot the tick's own
        // window belongs to the clock anchor (BTCUSDT), not to the market that was traded, so reporting
        // it would teach the model that ZKUSDT's features are Bitcoin's. Re-read the traded market.
        var candles = window;
        if (candles.Count == 0
            || !string.Equals(position.Symbol, bot.Symbol, StringComparison.OrdinalIgnoreCase))
        {
            try
            {
                candles = await marketData.Resolve(bot.Venue)
                    .GetClosedCandlesAsync(position.Symbol, bot.Interval, 300, cancellationToken);
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                logger.LogWarning(exception,
                    "Outcome window for {Symbol} could not be read; the sample is skipped", position.Symbol);
                return;
            }
        }

        try
        {
            var ack = await engine.RecordTradeOutcomeAsync(
                new MlTradeOutcome(
                    BotId: bot.Id.ToString(),
                    // The traded market, not the bot's registration symbol: a wildcard scanner carries `*`,
                    // and an outcome reported against `*` teaches the calibrator about a market that does
                    // not exist while the market that actually paid stays uncalibrated.
                    Symbol: position.Symbol,
                    Interval: bot.Interval,
                    ModelId: decision.ModelId ?? string.Empty,
                    ModelVersion: decision.ModelVersion ?? string.Empty,
                    Direction: (MlDirection)(int)position.Direction,
                    Candles: candles.Select(ToMlCandle).ToList(),
                    // The bracket actually traded, expressed as the percentages the engine re-prices with.
                    // A scanner bot's levels come from ATR multiples, so the bot's configured percentages
                    // describe a bracket that was never placed.
                    TakeProfitPercent: BracketPercent(position.AverageEntryPrice, position.TakeProfitPrice, bot.TakeProfitPercent),
                    StopLossPercent: BracketPercent(position.AverageEntryPrice, position.StopLossPrice, bot.StopLossPercent),
                    CloseReason: MapCloseReason(decision.ReasonCode) == PositionCloseReason.Manual
                        && decision.ReasonCode is "manual"
                        ? "manual"
                        : decision.ReasonCode,
                    RealizedPnl: position.RealizedPnl,
                    BarsHeld: (uint)Math.Max(0, position.BarsHeld),
                    DecisionCandleOpenTime: new DateTimeOffset(
                        DateTime.SpecifyKind(position.OpenedFromCandleOpenTime, DateTimeKind.Utc)),
                    ClosedAt: new DateTimeOffset(DateTime.SpecifyKind(position.ClosedAt.Value, DateTimeKind.Utc))),
                cancellationToken);

            if (ack is not null)
            {
                logger.LogInformation(
                    "Trade outcome reported for online learning | Bot {BotId} | status {Status} | stored {Stored} | training triggered {Triggered}",
                    bot.Id, ack.Status, ack.SamplesStored, ack.TrainingTriggered);
            }
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            // The engine's own failure to store a sample must never surface as a trading fault.
            logger.LogWarning(
                exception,
                "Trade outcome report failed | Bot {BotId} | the sample is lost, trading is unaffected",
                bot.Id);
        }
    }

    // ── construction helpers ─────────────────────────────────────────────────────

    private OrderIntent? BuildIntent(
        TradingBot bot,
        StrategyDecision decision,
        BotDecisionAction action,
        BotPosition? openPosition,
        InstrumentRules rules)
    {
        var referencePrice = decision.EntryPrice ?? 0m;
        if (referencePrice <= 0)
            return null;

        decimal quantity;
        OrderSide side;
        TradeDirection direction;

        if (action == BotDecisionAction.Open)
        {
            direction = decision.Direction;
            if (direction is not (TradeDirection.Long or TradeDirection.Short))
                return null;

            side = direction == TradeDirection.Long ? OrderSide.Buy : OrderSide.Sell;
            // A venue caps order size per instrument (Binance's MARKET_LOT_SIZE.maxQty). Sizing past that
            // cap is not a risk appetite the operator can opt into — the venue rejects the order and the
            // intent dies with a rule violation that had nothing to do with risk. The cap belongs in the
            // sizing step, so the order that reaches the risk engine is one the venue can actually fill.
            var budgeted = bot.QuoteNotionalPerTrade / referencePrice;
            if (rules.MaxQuantity > 0m && budgeted > rules.MaxQuantity)
                budgeted = rules.MaxQuantity;
            quantity = rules.QuantizeQuantity(budgeted);
        }
        else // Close
        {
            if (openPosition is null || openPosition.Quantity <= 0)
                return null;

            direction = openPosition.Direction;
            side = direction == TradeDirection.Long ? OrderSide.Sell : OrderSide.Buy;
            quantity = rules.QuantizeQuantity(openPosition.Quantity);
        }

        if (quantity <= 0)
            return null;

        // Budget the estimated notional for the assumed fee and the bot's slippage tolerance, so the
        // notional and balance checks reserve enough for the round trip rather than the bare fill.
        var buffer = 1m + (AssumedFeeBps + Math.Max(0, bot.MaxSlippageBps)) / 10_000m;
        var estimatedNotional = quantity * referencePrice * buffer;

        return new OrderIntent
        {
            StrategyDecisionId = decision.Id,
            BotId = bot.Id,
            OperatingMode = bot.OperatingMode,
            ClientOrderId = TradingIdentifiers.ClientOrderId(decision.Id),
            // The market being traded, not the bot's registration symbol: a wildcard scanner carries `*`
            // and the intents it produces must name the proposal's market or the risk engine reads the
            // order as "an intent for * on a bot trading ARBUSDT" and denies its own provenance check.
            Symbol = string.IsNullOrWhiteSpace(decision.Symbol) ? bot.Symbol : decision.Symbol,
            Direction = direction,
            Side = side,
            Type = OrderType.Market,
            Quantity = quantity,
            LimitPrice = null,
            TakeProfitPrice = action == BotDecisionAction.Open ? decision.TakeProfitPrice : null,
            StopLossPrice = action == BotDecisionAction.Open ? decision.StopLossPrice : null,
            TimeInForce = null,
            ReferencePrice = referencePrice,
            Leverage = bot.Leverage,
            EstimatedNotional = estimatedNotional,
            Status = OrderIntentStatus.Draft,
        };
    }

    private async Task PersistWindowAsync(
        TradingBot bot,
        IReadOnlyList<MarketCandleData> window,
        CancellationToken cancellationToken)
    {
        var openTimes = window.Select(c => c.OpenTime.UtcDateTime).ToList();

        var existing = await candles.TableNoTracking
            .Where(c => c.Venue == bot.Venue
                        && c.Symbol == bot.Symbol
                        && c.Interval == bot.Interval
                        && openTimes.Contains(c.OpenTime))
            .Select(c => c.OpenTime)
            .ToListAsync(cancellationToken);

        var known = existing.ToHashSet();
        var toInsert = window
            .Where(c => !known.Contains(c.OpenTime.UtcDateTime))
            .Select(c => new MarketCandle
            {
                Venue = bot.Venue,
                Symbol = bot.Symbol,
                Interval = bot.Interval,
                OpenTime = c.OpenTime.UtcDateTime,
                CloseTime = c.CloseTime.UtcDateTime,
                Open = c.Open,
                High = c.High,
                Low = c.Low,
                Close = c.Close,
                Volume = c.Volume,
                QuoteVolume = c.QuoteVolume,
                TradeCount = c.TradeCount,
                IsClosed = true,
                FetchedAt = DateTime.UtcNow,
            })
            .ToList();

        if (toInsert.Count > 0)
            await candles.AddRangeAsync(toInsert, saveNow: true, cancellationToken);
    }

    private async Task<StrategyDecision> PersistDecisionAsync(
        TradingBot bot,
        MlBotDecision response,
        BotDecisionAction action,
        DateTime candleOpenTime,
        CancellationToken cancellationToken)
    {
        // A bot configured in ATR multiples prices its bracket from the engine's own ATR, replacing
        // the percent-derived levels the engine computed. The engine still priced the bet with its
        // percent barriers (the wire contract), so the probabilities correspond to those — replacing
        // the *levels* keeps the recorded geometry consistent with what will actually work at the
        // venue, while the confidence stays the engine's answer to the percent bet it was asked.
        var effectiveLevels = AtrBrackets.Resolve(
            bot.TakeProfitAtrMultiple,
            bot.StopLossAtrMultiple,
            response.Levels,
            isLong: response.Direction == MlDirection.Long);

        var decision = new StrategyDecision
        {
            BotId = bot.Id,
            OperatingMode = bot.OperatingMode,
            Symbol = bot.Symbol,
            Interval = bot.Interval,
            CandleOpenTime = candleOpenTime,
            CandleWindowDigest = response.InputDigestSha256,
            Action = action,
            Direction = (TradeDirection)(int)response.Direction,
            ReasonCode = response.ReasonCode,
            Confidence = response.Confidence,
            LongConfidence = 0,
            ShortConfidence = 0,
            ExpectedValue = response.ExpectedValue,
            ProbabilityTakeProfitFirst = response.Probabilities.TakeProfitFirst,
            ProbabilityStopLossFirst = response.Probabilities.StopLossFirst,
            ProbabilityTimeout = response.Probabilities.Timeout,
            EntryPrice = response.Levels?.EntryPrice,
            TakeProfitPrice = effectiveLevels.TakeProfitPrice,
            StopLossPrice = effectiveLevels.StopLossPrice,
            Atr = response.Levels?.Atr,
            RiskRewardRatio = response.Levels?.RiskRewardRatio,
            TakeProfitAtr = response.Levels?.TakeProfitAtr,
            StopLossAtr = response.Levels?.StopLossAtr,
            ModelId = response.ModelId,
            ModelVersion = response.ModelVersion,
            ModelTrainedAt = response.ModelTrainedAt?.UtcDateTime,
            UsedWildcardModel = response.UsedWildcardModel,
            BarrierExtrapolated = response.BarrierExtrapolated,
            Warning = string.IsNullOrWhiteSpace(response.Warning) ? null : response.Warning,
            ValidUntil = response.ValidUntil?.UtcDateTime,
            EngineRequestId = response.RequestId,
            ProcessingMilliseconds = response.ProcessingMilliseconds,
        };

        await decisions.AddAsync(decision, saveNow: true, cancellationToken);
        return decision;
    }

    private async Task PersistRiskDecisionAsync(
        TradingBot bot,
        OrderIntent intent,
        RiskVerdict verdict,
        CancellationToken cancellationToken)
    {
        var row = new RiskDecision
        {
            OrderIntentId = intent.Id,
            BotId = bot.Id,
            Allowed = verdict.Allowed,
            FailedChecksCsv = verdict.FailedChecksCsv,
            Detail = verdict.Detail,
            SnapshotJson = verdict.SnapshotJson,
            EvaluatedAt = DateTime.UtcNow,
        };
        await riskDecisions.AddAsync(row, saveNow: true, cancellationToken);
    }

    private async Task AdjustBracketAsync(
        TradingBot bot,
        BotPosition? openPosition,
        MlBotDecision response,
        string correlationId,
        CancellationToken cancellationToken)
    {
        if (openPosition is null || response.Levels is null)
            return;

        // Same override as a fresh decision: an ATR-configured bot trails in ATR multiples, not
        // percent. The direction is the open position's — that is the side the bracket protects.
        var effectiveLevels = AtrBrackets.Resolve(
            bot.TakeProfitAtrMultiple,
            bot.StopLossAtrMultiple,
            response.Levels,
            isLong: openPosition.Direction == TradeDirection.Long);

        openPosition.TakeProfitPrice = effectiveLevels.TakeProfitPrice;
        openPosition.StopLossPrice = effectiveLevels.StopLossPrice;
        await positions.UpdateAsync(openPosition, saveNow: true, cancellationToken);

        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.PositionChanged, bot.OperatingMode,
                $"Bracket moved to TP {response.Levels.TakeProfitPrice} / SL {response.Levels.StopLossPrice}",
                BotId: bot.Id, Symbol: bot.Symbol, BotPositionId: openPosition.Id),
            cancellationToken);
    }

    /// <summary>
    /// Finishes any order whose fill was recorded but whose position never got settled.
    /// </summary>
    /// <remarks>
    /// The stall this exists for is real: a close was placed, the venue filled it, and the tick ended before
    /// <see cref="ApplyToPositionAsync"/> ran — leaving the intent in Submitted and the position open on a
    /// book that had already gone flat. This step is idempotent (a settled intent is no longer Submitted),
    /// so running it on every tick costs one indexed read and removes a whole class of "the bot thinks it
    /// is long something it sold yesterday".
    /// </remarks>
    private async Task SettleStrandedIntentsAsync(
        TradingBot bot, string correlationId, CancellationToken cancellationToken)
    {
        var settledFloor = DateTime.UtcNow.AddSeconds(-10);
        var stranded = await intents.Table
            .Where(i => i.BotId == bot.Id
                        && (i.Status == OrderIntentStatus.Submitted || i.Status == OrderIntentStatus.PartiallyFilled)
                        && i.SubmittedAt != null
                        && i.SubmittedAt < settledFloor
                        && !i.IsDeleted)
            .OrderByDescending(i => i.CreatedAt)
            .Take(3)
            .ToListAsync(cancellationToken);

        if (stranded.Count == 0)
            return;

        var open = await LoadOpenPositionAsync(bot, cancellationToken);

        foreach (var intent in stranded)
        {
            var order = await exchangeOrders.TableNoTracking
                .FirstOrDefaultAsync(o => o.OrderIntentId == intent.Id, cancellationToken);
            if (order is null || order.FilledQuantity <= 0)
                continue;

            var decision = await decisions.TableNoTracking
                .FirstOrDefaultAsync(d => d.Id == intent.StrategyDecisionId, cancellationToken);
            if (decision is null)
                continue;

            var fillRows = await fills.TableNoTracking
                .Where(f => f.ExchangeOrderId == order.Id)
                .ToListAsync(cancellationToken);
            if (fillRows.Count == 0)
                continue;

            if (open is not null && decision.Action == BotDecisionAction.Close)
            {
                var settled = await ApplyToPositionAsync(
                    bot, decision, intent, order, fillRows, BotDecisionAction.Close, open, cancellationToken);

                // A settled close is a labelled example. Without this the fast calibration loop never sees
                // a trade that was rescued by reconciliation — the very trades most worth learning from.
                if (settled is not null)
                    await ReportTradeOutcomeAsync(
                        bot, decision, settled, Array.Empty<MarketCandleData>(), correlationId,
                        CancellationToken.None);
            }

            intent.Status = OrderIntentStatus.Filled;
            intent.CompletedAt = DateTime.UtcNow;
            await intents.UpdateAsync(intent, saveNow: true, cancellationToken);

            await audit.AppendAsync(
                new BotAuditEntry(
                    correlationId, BotAuditEventType.OrderStateChanged, bot.OperatingMode,
                    $"Settled stranded intent {intent.ClientOrderId} from its recorded fill",
                    BotId: bot.Id, Symbol: intent.Symbol, StrategyDecisionId: decision.Id,
                    OrderIntentId: intent.Id, ExchangeOrderId: order.Id),
                cancellationToken);
        }
    }

    private async Task<BotPosition?> LoadOpenPositionAsync(TradingBot bot, CancellationToken cancellationToken) =>
        await positions.Table.FirstOrDefaultAsync(
            p => p.BotId == bot.Id
                 && p.OperatingMode == bot.OperatingMode
                 && p.Status == PositionStatus.Open,
            cancellationToken);

    private async Task MarkEvaluatedAsync(TradingBot bot, DateTime candleOpenTime, CancellationToken cancellationToken)
    {
        bot.LastEvaluatedCandleOpenTime = candleOpenTime;
        bot.LastTickAt = DateTime.UtcNow;
        await bots.UpdateAsync(bot, saveNow: true, cancellationToken);
    }

    private async Task FaultBotAsync(
        TradingBot bot,
        string correlationId,
        string reason,
        CancellationToken cancellationToken)
    {
        logger.LogError("Bot {BotId} faulted: {Reason}", bot.Id, reason);

        bot.Status = BotStatus.Faulted;
        bot.StatusReason = reason;
        bot.FaultedAt = DateTime.UtcNow;
        await bots.UpdateAsync(bot, saveNow: true, CancellationToken.None);

        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.BotFaulted, bot.OperatingMode,
                $"Bot faulted: {reason}", BotId: bot.Id, Symbol: bot.Symbol),
            CancellationToken.None);
    }

    // ── wire mapping ─────────────────────────────────────────────────────────────

    private static MlCandle ToMlCandle(MarketCandleData c) =>
        new(c.OpenTime, c.Open, c.High, c.Low, c.Close, c.Volume);

    private static MlOpenPosition ToMlPosition(BotPosition p) =>
        new(
            (MlDirection)(int)p.Direction,
            p.AverageEntryPrice,
            p.Quantity,
            p.OpenedAt,
            p.TakeProfitPrice,
            p.StopLossPrice,
            (uint)Math.Max(0, p.BarsHeld));

    private static PositionCloseReason MapCloseReason(string reasonCode) => reasonCode switch
    {
        "take_profit_touched" => PositionCloseReason.TakeProfitTouched,
        "stop_loss_touched" => PositionCloseReason.StopLossTouched,
        "max_holding_periods_reached" => PositionCloseReason.MaxHoldingPeriodsReached,
        "direction_reversed" => PositionCloseReason.DirectionReversed,
        _ => PositionCloseReason.Manual,
    };
}

/// <summary>
/// Raised for the two conditions a bot must not trade through: a candle window that cannot be fetched,
/// and an ambiguous order outcome. Caught in <see cref="BotTickExecutor.ExecuteAsync"/>, which faults the
/// bot rather than retrying.
/// </summary>
public sealed class BotFaultException(string message) : Exception(message);
