using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Security;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
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
        var source = marketData.Resolve(bot.Venue);
        IReadOnlyList<MarketCandleData> window;
        try
        {
            window = await source.GetClosedCandlesAsync(
                bot.Symbol, bot.Interval, options.Value.CandleWindowSize, cancellationToken);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            throw new BotFaultException(
                $"the {bot.Venue} candle window for {bot.Symbol} {bot.Interval} could not be fetched: " +
                $"{exception.Message}");
        }

        if (window.Count == 0)
            throw new BotFaultException($"the {bot.Venue} source returned no candles for {bot.Symbol}");

        var newest = window[^1];
        var candleOpenTime = newest.OpenTime.UtcDateTime;

        // ── idempotency: has this candle already been decided on? ────────────────
        if (bot.LastEvaluatedCandleOpenTime == candleOpenTime)
            return new TickOutcome(TickResult.AlreadyEvaluated, correlationId, Message: "candle already evaluated");

        var alreadyDecided = await decisions.TableNoTracking
            .AnyAsync(d => d.BotId == bot.Id && d.CandleOpenTime == candleOpenTime, cancellationToken);
        if (alreadyDecided)
        {
            await MarkEvaluatedAsync(bot, candleOpenTime, cancellationToken);
            return new TickOutcome(TickResult.AlreadyEvaluated, correlationId, Message: "decision already exists");
        }

        // ── 3. persist the window (only the candles not already stored) ──────────
        await PersistWindowAsync(bot, window, cancellationToken);
        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.CandleWindowRecorded, bot.OperatingMode,
                $"Recorded {window.Count} {bot.Interval} candles for {bot.Symbol} up to {candleOpenTime:O}",
                BotId: bot.Id, Symbol: bot.Symbol, CandleOpenTime: candleOpenTime),
            cancellationToken);

        // ── 4. consult the engine ────────────────────────────────────────────────
        var openPosition = await LoadOpenPositionAsync(bot, cancellationToken);

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
                    bot.MinimumConfidence),
                Position: openPosition is null ? null : ToMlPosition(openPosition),
                ExpectedModelVersion: bot.ExpectedModelVersion,
                RequestId: correlationId),
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

        // ── 6. build the intent (deterministic client order id) ──────────────────
        var rules = await instrumentRules.GetRulesAsync(bot.Venue, bot.Symbol, cancellationToken);
        var intent = BuildIntent(bot, decision, action, openPosition, rules);
        if (intent is null)
        {
            // The engine advised OPEN/CLOSE but the levels or position needed to construct an order are
            // absent. Recorded via the decision; nothing is placed.
            return new TickOutcome(TickResult.Hold, correlationId, decision.Id, Action: action,
                Message: "no order could be constructed from the decision");
        }

        await intents.AddAsync(intent, saveNow: true, cancellationToken);
        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.OrderIntentCreated, bot.OperatingMode,
                $"Intent {intent.ClientOrderId}: {intent.Side} {intent.Quantity} {bot.Symbol} @ ~{intent.ReferencePrice}",
                BotId: bot.Id, Symbol: bot.Symbol, StrategyDecisionId: decision.Id,
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
            bot, decision, intent, broker, creds, rules, action, openPosition, correlationId, cancellationToken);
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
                intent.TakeProfitPrice, intent.StopLossPrice, intent.TimeInForce, bot.MaxSlippageBps),
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
                Symbol = bot.Symbol,
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
        openPosition.Quantity = 0m;
        openPosition.CloseReason = MapCloseReason(decision.ReasonCode);
        await positions.UpdateAsync(openPosition, saveNow: true, cancellationToken);
        return openPosition;
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
            quantity = rules.QuantizeQuantity(bot.QuoteNotionalPerTrade / referencePrice);
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
            Symbol = bot.Symbol,
            Direction = direction,
            Side = side,
            Type = OrderType.Market,
            Quantity = quantity,
            LimitPrice = null,
            TakeProfitPrice = action == BotDecisionAction.Open ? decision.TakeProfitPrice : null,
            StopLossPrice = action == BotDecisionAction.Open ? decision.StopLossPrice : null,
            TimeInForce = null,
            ReferencePrice = referencePrice,
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
            TakeProfitPrice = response.Levels?.TakeProfitPrice,
            StopLossPrice = response.Levels?.StopLossPrice,
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

        openPosition.TakeProfitPrice = response.Levels.TakeProfitPrice;
        openPosition.StopLossPrice = response.Levels.StopLossPrice;
        await positions.UpdateAsync(openPosition, saveNow: true, cancellationToken);

        await audit.AppendAsync(
            new BotAuditEntry(
                correlationId, BotAuditEventType.PositionChanged, bot.OperatingMode,
                $"Bracket moved to TP {response.Levels.TakeProfitPrice} / SL {response.Levels.StopLossPrice}",
                BotId: bot.Id, Symbol: bot.Symbol, BotPositionId: openPosition.Id),
            cancellationToken);
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
