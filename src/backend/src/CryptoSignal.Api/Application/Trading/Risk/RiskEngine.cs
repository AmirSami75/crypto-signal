using System.Text.Json;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.Application.Trading.Risk;

/// <summary>
/// Evaluates the pre-trade checks of <c>docs/LIVE_TRADING_SAFETY.md</c> against one frozen
/// <see cref="RiskSnapshot"/>.
/// </summary>
/// <remarks>
/// <para>
/// Two properties hold for every check below, and both are load-bearing:
/// </para>
/// <para>
/// <b>Nothing re-reads state.</b> <see cref="BuildSnapshotAsync"/> is the only method that touches the
/// database. Each check is a pure function of the snapshot, so the set of checks describes a single
/// portfolio at a single instant rather than a portfolio that drifted while being inspected.
/// </para>
/// <para>
/// <b>Zero denies.</b> Every numeric limit is compared with <see cref="Effective(decimal, decimal)"/>
/// semantics — an unset limit is not an infinite limit. The engine is written so that the way to make it
/// permissive is to configure it, never to leave it alone.
/// </para>
/// <para>
/// Denials are collected rather than short-circuited. An operator fixing a misconfigured bot wants all
/// four reasons at once, not one per redeploy.
/// </para>
/// </remarks>
public sealed class RiskEngine(
    IRepo<BotPosition> positions,
    IRepo<OrderIntent> intents,
    IRepo<KillSwitch> killSwitches,
    IRepo<BotRun> runs,
    IOptions<TradingRiskOptions> options,
    ILogger<RiskEngine> logger) : IRiskEngine, IScopedSvcMarker
{
    private static readonly JsonSerializerOptions SnapshotJson = new() { WriteIndented = false };

    public async Task<RiskVerdict> EvaluateAsync(
        RiskEvaluationContext context,
        CancellationToken cancellationToken)
    {
        RiskSnapshot snapshot;

        try
        {
            snapshot = await BuildSnapshotAsync(context, cancellationToken);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            // A snapshot that cannot be read is not an inconclusive result — it is a denial. Every check
            // depends on it, so none of them can be said to have passed.
            logger.LogError(
                exception,
                "Risk snapshot could not be built for bot {BotId}; denying intent {ClientOrderId}",
                context.Bot.Id,
                context.Intent.ClientOrderId);

            return new RiskVerdict(
                Allowed: false,
                FailedChecks: Enum.GetValues<RiskCheck>(),
                Detail: $"The risk snapshot could not be read, so no check could be evaluated: {exception.Message}",
                SnapshotJson: "{}");
        }

        var failures = new List<(RiskCheck Check, string Reason)>();

        void Deny(RiskCheck check, string reason) => failures.Add((check, reason));

        CheckModeAndStrategy(snapshot, Deny);
        CheckModelVersion(snapshot, Deny);
        CheckSignalProvenance(snapshot, context, Deny);
        CheckSignalNotAlreadyActedOn(snapshot, Deny);
        CheckDataFreshness(snapshot, Deny);
        CheckMarket(snapshot, Deny);
        CheckOrderParameters(snapshot, Deny);
        CheckNotional(snapshot, Deny);
        CheckExposure(snapshot, Deny);
        CheckLossAndDrawdown(snapshot, Deny);
        CheckFrequency(snapshot, Deny);
        CheckBalance(snapshot, Deny);
        CheckConnectivity(snapshot, Deny);
        CheckKillSwitches(snapshot, Deny);
        CheckHumanApproval(snapshot, Deny);
        CheckModelOutputUsable(snapshot, Deny);

        var failed = failures.Select(f => f.Check).Distinct().OrderBy(c => (int)c).ToArray();
        var detail = failures.Count == 0
            ? null
            : string.Join(" | ", failures.Select(f => $"{f.Check}: {f.Reason}"));

        if (failed.Length > 0)
        {
            logger.LogWarning(
                "Risk denied {ClientOrderId} for bot {BotId} on {FailedCount} check(s): {FailedChecks}",
                snapshot.ClientOrderId,
                snapshot.BotId,
                failed.Length,
                string.Join(',', failed));
        }

        return new RiskVerdict(
            Allowed: failed.Length == 0,
            FailedChecks: failed,
            Detail: detail,
            SnapshotJson: JsonSerializer.Serialize(snapshot, SnapshotJson));
    }

    // ── the one and only read of state ───────────────────────────────────────────

    private async Task<RiskSnapshot> BuildSnapshotAsync(
        RiskEvaluationContext context,
        CancellationToken cancellationToken)
    {
        var (bot, decision, intent, rules, newestCandleOpenTime, balance) = context;
        var limits = options.Value;
        var now = DateTime.UtcNow;
        var dayStart = new DateTime(now.Year, now.Month, now.Day, 0, 0, 0, DateTimeKind.Utc);

        // Mode isolation is a filter on every read, not a convention: a paper position must never
        // count toward a sandbox bot's exposure, or the two portfolios silently become one.
        var openPositions = await positions.TableNoTracking
            .Where(p => p.BotId == bot.Id
                        && p.OperatingMode == bot.OperatingMode
                        && p.Status == PositionStatus.Open)
            .Select(p => new { p.Symbol, p.EntryNotional, p.UnrealizedPnl })
            .ToListAsync(cancellationToken);

        var realizedToday = await positions.TableNoTracking
            .Where(p => p.BotId == bot.Id
                        && p.OperatingMode == bot.OperatingMode
                        && p.ClosedAt != null
                        && p.ClosedAt >= dayStart)
            .SumAsync(p => (decimal?)p.RealizedPnl, cancellationToken) ?? 0m;

        // Orders "today" counts intents that actually reached a venue. A risk-denied intent consumed no
        // quota — counting it would let a run of denials starve the bot of its own daily allowance.
        var ordersToday = await intents.TableNoTracking
            .CountAsync(
                i => i.BotId == bot.Id
                     && i.OperatingMode == bot.OperatingMode
                     && i.SubmittedAt != null
                     && i.SubmittedAt >= dayStart
                     && i.Id != intent.Id,
                cancellationToken);

        var ambiguous = await intents.TableNoTracking
            .CountAsync(
                i => i.BotId == bot.Id
                     && i.OperatingMode == bot.OperatingMode
                     && i.Status == OrderIntentStatus.Ambiguous,
                cancellationToken);

        var alreadyActedOn = await intents.TableNoTracking
            .AnyAsync(
                i => i.StrategyDecisionId == decision.Id && i.Id != intent.Id,
                cancellationToken);

        // Any engaged switch whose scope covers this bot blocks it. Evaluated as one query so a switch
        // engaged mid-evaluation cannot be seen by one check and missed by another.
        var engaged = await killSwitches.TableNoTracking
            .Where(k => k.IsEngaged
                        && (k.Scope == KillSwitchScope.Global
                            || (k.Scope == KillSwitchScope.OperatingMode &&
                                k.ScopeOperatingMode == bot.OperatingMode)
                            || (k.Scope == KillSwitchScope.Exchange && k.ScopeVenue == bot.Venue)
                            || (k.Scope == KillSwitchScope.Bot && k.ScopeBotId == bot.Id)
                            || (k.Scope == KillSwitchScope.Symbol && k.ScopeSymbol == bot.Symbol)))
            .Select(k => new { k.Scope, k.Reason })
            .ToListAsync(cancellationToken);

        var consecutiveFailures = await runs.TableNoTracking
            .Where(r => r.BotId == bot.Id && r.EndedAt == null)
            .OrderByDescending(r => r.StartedAt)
            .Select(r => (int?)r.ConsecutiveFailureCount)
            .FirstOrDefaultAsync(cancellationToken) ?? 0;

        var intervalSeconds = CandleInterval.TryToTimeSpan(bot.Interval, out var intervalSpan)
            ? intervalSpan.TotalSeconds
            : 0d;

        var modeEnabled = limits.EnabledOperatingModes
            .Any(m => string.Equals(m, bot.OperatingMode.ToString(), StringComparison.OrdinalIgnoreCase));

        var symbolAllowed = limits.AllowedSymbols
            .Any(s => string.Equals(s, bot.Symbol, StringComparison.OrdinalIgnoreCase));

        // An empty approved-version list means "do not pin", which cannot overspend. Every other empty
        // list in the options denies.
        var versionApproved = limits.ApprovedModelVersions.Length == 0
                              || limits.ApprovedModelVersions.Any(v =>
                                  string.Equals(v, decision.ModelVersion, StringComparison.Ordinal));

        return new RiskSnapshot
        {
            TakenAt = now,

            BotId = bot.Id,
            BotName = bot.Name,
            BotStatus = bot.Status,
            OperatingMode = bot.OperatingMode,
            Venue = bot.Venue,
            Symbol = bot.Symbol,
            Interval = bot.Interval,

            StrategyDecisionId = decision.Id,
            OrderIntentId = intent.Id,
            ClientOrderId = intent.ClientOrderId,
            Direction = intent.Direction,
            Side = intent.Side,
            OrderType = intent.Type,
            TimeInForce = intent.TimeInForce,
            Quantity = intent.Quantity,
            LimitPrice = intent.LimitPrice,
            ReferencePrice = intent.ReferencePrice,
            EstimatedNotional = intent.EstimatedNotional,

            ModelId = decision.ModelId,
            ModelVersion = decision.ModelVersion,
            BotExpectedModelVersion = bot.ExpectedModelVersion,
            BarrierExtrapolated = decision.BarrierExtrapolated,
            UsedWildcardModel = decision.UsedWildcardModel,
            Confidence = decision.Confidence,
            ExpectedValue = decision.ExpectedValue,
            DecisionCandleOpenTime = decision.CandleOpenTime,
            DecisionValidUntil = decision.ValidUntil,
            DecisionSymbol = decision.Symbol,
            DecisionInterval = decision.Interval,
            DecisionOperatingMode = decision.OperatingMode,
            DecisionBotId = decision.BotId,

            NewestCandleOpenTime = newestCandleOpenTime,
            CandleAgeSeconds = (now - newestCandleOpenTime).TotalSeconds,
            IntervalSeconds = intervalSeconds,
            MaxCandleAgeSeconds = intervalSeconds * limits.MaxCandleAgeIntervals,

            InstrumentTradable = rules.IsTradable,
            VenueSupportsMarketOrders = rules.SupportsMarketOrders,
            TickSize = rules.TickSize,
            StepSize = rules.StepSize,
            MinQuantity = rules.MinQuantity,
            MaxQuantity = rules.MaxQuantity,
            VenueMinNotional = rules.MinNotional,

            OpenPositionCount = openPositions.Count,
            OpenPositionNotional = openPositions.Sum(p => p.EntryNotional),
            HasOpenPositionForSymbol = openPositions.Any(p =>
                string.Equals(p.Symbol, bot.Symbol, StringComparison.OrdinalIgnoreCase)),
            OrdersToday = ordersToday,
            RealizedPnlToday = realizedToday,
            OpenUnrealizedPnl = openPositions.Sum(p => p.UnrealizedPnl ?? 0m),
            AvailableQuoteBalance = balance,

            ConsecutiveFailures = consecutiveFailures,
            UnresolvedAmbiguousIntents = ambiguous,
            DecisionAlreadyActedOn = alreadyActedOn,
            EngagedKillSwitchScopes = engaged
                .Select(k => $"{k.Scope}: {k.Reason}")
                .ToArray(),

            LiveExecutionAllowed = limits.AllowLiveExecution,
            ModeEnabled = modeEnabled,
            SymbolAllowlisted = symbolAllowed,
            ShortingAllowed = limits.AllowShorting,
            SpotOnly = limits.SpotOnly,
            ModelVersionApproved = versionApproved,

            EffectiveMaxOrderNotional = Effective(bot.MaxOrderNotional, limits.MaxOrderNotional),
            EffectiveMaxPositionNotional = Effective(bot.MaxPositionNotional, limits.MaxPositionNotional),
            EffectiveMaxDailyLoss = Effective(bot.MaxDailyLoss, limits.MaxDailyLoss),
            EffectiveMaxOrdersPerDay = Effective(bot.MaxOrdersPerDay, limits.MaxOrdersPerDay),
            EffectiveMaxConcurrentPositions =
                Effective(bot.MaxConcurrentPositions, limits.MaxConcurrentPositions),
            EffectiveMaxConsecutiveFailures =
                Effective(bot.MaxConsecutiveFailures, limits.MaxConsecutiveFailures),
            BotMaxDrawdown = bot.MaxDrawdown,
            BotMaxSlippageBps = bot.MaxSlippageBps,
            BotMinimumConfidence = bot.MinimumConfidence,
        };
    }

    /// <summary>
    /// Resolves a bot limit against the platform ceiling: the tighter of the two, where zero on either
    /// side means zero.
    /// </summary>
    /// <remarks>
    /// This is where "a zero or missing limit denies" is actually implemented, and the asymmetry is
    /// deliberate. <c>Math.Min</c> alone would give an unset bot limit of 0 the tightest possible value,
    /// which is correct — but an unset <em>platform</em> ceiling of 0 must also deny rather than defer to
    /// the bot's number, and only the explicit zero test gives that.
    /// </remarks>
    private static decimal Effective(decimal botLimit, decimal platformLimit) =>
        botLimit <= 0 || platformLimit <= 0 ? 0m : Math.Min(botLimit, platformLimit);

    private static int Effective(int botLimit, int platformLimit) =>
        botLimit <= 0 || platformLimit <= 0 ? 0 : Math.Min(botLimit, platformLimit);

    // ── the checks, each a pure function of the snapshot ─────────────────────────

    private static void CheckModeAndStrategy(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.ModeAndStrategyEnabled;

        if (s.BotStatus != BotStatus.Active)
            deny(check, $"the bot is {s.BotStatus}, and only Active bots may place orders");

        if (!s.ModeEnabled)
            deny(check, $"operating mode {s.OperatingMode} is not in Trading:Risk:EnabledOperatingModes");

        // Live is denied here regardless of configuration: the promotion gates it requires are not
        // implemented in this codebase, so there is no configuration that should make it reachable.
        if (s.OperatingMode == OperatingMode.Live)
            deny(check, "live execution is not implemented on this platform and is denied unconditionally");
    }

    private static void CheckModelVersion(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.ModelVersionApproved;

        if (string.IsNullOrWhiteSpace(s.ModelVersion))
            deny(check, "the decision carries no model version, so it cannot be attributed to a model");

        if (!s.ModelVersionApproved)
            deny(check, $"model version '{s.ModelVersion}' is not in Trading:Risk:ApprovedModelVersions");

        // A bot that pins a version must stop after a retrain rather than inherit a model its limits
        // were never tuned against.
        if (!string.IsNullOrWhiteSpace(s.BotExpectedModelVersion)
            && !string.Equals(s.BotExpectedModelVersion, s.ModelVersion, StringComparison.Ordinal))
        {
            deny(check,
                $"the bot pins model version '{s.BotExpectedModelVersion}' but the decision came from " +
                $"'{s.ModelVersion}'");
        }
    }

    private static void CheckSignalProvenance(
        RiskSnapshot s,
        RiskEvaluationContext context,
        Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.SignalProvenance;

        if (s.DecisionBotId != s.BotId)
            deny(check, "the decision belongs to a different bot");

        if (!string.Equals(s.DecisionSymbol, s.Symbol, StringComparison.OrdinalIgnoreCase))
            deny(check, $"the decision is for {s.DecisionSymbol} but the bot trades {s.Symbol}");

        if (!string.Equals(s.DecisionInterval, s.Interval, StringComparison.OrdinalIgnoreCase))
            deny(check, $"the decision is on the {s.DecisionInterval} interval but the bot runs {s.Interval}");

        if (s.DecisionOperatingMode != s.OperatingMode)
            deny(check, $"the decision was made in {s.DecisionOperatingMode} but the bot runs {s.OperatingMode}");

        if (context.Intent.StrategyDecisionId != s.StrategyDecisionId)
            deny(check, "the intent does not reference the decision being evaluated");

        if (!string.Equals(context.Intent.Symbol, s.Symbol, StringComparison.OrdinalIgnoreCase))
            deny(check, $"the intent is for {context.Intent.Symbol} but the bot trades {s.Symbol}");

        if (context.Intent.OperatingMode != s.OperatingMode)
            deny(check, "the intent's operating mode does not match the bot's");

        // The candle must be closed. Acting on an in-progress candle means the features were computed
        // from a bar that has not finished moving, which is look-ahead by another name.
        if (s.IntervalSeconds > 0
            && s.DecisionCandleOpenTime.AddSeconds(s.IntervalSeconds) > s.TakenAt)
        {
            deny(check,
                $"the decision candle opening {s.DecisionCandleOpenTime:O} has not closed yet");
        }
    }

    private static void CheckSignalNotAlreadyActedOn(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        if (s.DecisionAlreadyActedOn)
        {
            deny(RiskCheck.SignalNotAlreadyActedOn,
                "another order intent already exists for this decision; one decision authorises one order");
        }
    }

    private static void CheckDataFreshness(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.DataFreshness;

        if (s.IntervalSeconds <= 0)
            deny(check, $"interval '{s.Interval}' could not be parsed, so candle age cannot be bounded");

        if (s.MaxCandleAgeSeconds <= 0)
            deny(check, "Trading:Risk:MaxCandleAgeIntervals is unset, so no freshness bound exists");
        else if (s.CandleAgeSeconds > s.MaxCandleAgeSeconds)
            deny(check,
                $"the newest candle is {s.CandleAgeSeconds:F0}s old, beyond the {s.MaxCandleAgeSeconds:F0}s bound");

        if (s.DecisionValidUntil is { } validUntil && validUntil <= s.TakenAt)
            deny(check, $"the decision expired at {validUntil:O}");

        if (s.AvailableQuoteBalance is null)
            deny(check, "the account balance could not be read, so it is not fresh");
    }

    private static void CheckMarket(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.MarketAllowlistedAndTradable;

        if (!s.SymbolAllowlisted)
            deny(check, $"{s.Symbol} is not in Trading:Risk:AllowedSymbols");

        if (!s.InstrumentTradable)
            deny(check, $"{s.Symbol} is not currently tradable at {s.Venue}");
    }

    private static void CheckOrderParameters(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.OrderParametersSupported;

        if (s.Direction == TradeDirection.Flat)
            deny(check, "a FLAT direction describes no order");

        // Spot cannot sell what it does not hold. This is arithmetic, not appetite, so it denies before
        // any preference about shorting is consulted.
        if (s.Direction == TradeDirection.Short)
        {
            if (s.SpotOnly)
                deny(check, "the platform is configured spot-only and a spot account cannot short");
            else if (!s.ShortingAllowed)
                deny(check, "Trading:Risk:AllowShorting is false");
        }

        if (s.Quantity <= 0)
            deny(check, "quantity must be greater than zero");
        else
        {
            if (s.MinQuantity > 0 && s.Quantity < s.MinQuantity)
                deny(check, $"quantity {s.Quantity} is below the venue minimum {s.MinQuantity}");

            if (s.MaxQuantity > 0 && s.Quantity > s.MaxQuantity)
                deny(check, $"quantity {s.Quantity} exceeds the venue maximum {s.MaxQuantity}");

            if (!InstrumentRules.IsOnGrid(s.Quantity, s.StepSize))
                deny(check, $"quantity {s.Quantity} is not a multiple of the step size {s.StepSize}");
        }

        if (s.ReferencePrice <= 0)
            deny(check, "the reference price must be greater than zero");

        switch (s.OrderType)
        {
            case OrderType.Market:
                if (!s.VenueSupportsMarketOrders)
                    deny(check, $"{s.Venue} does not accept market orders for {s.Symbol}");
                if (s.LimitPrice is not null)
                    deny(check, "a market order must not carry a limit price");
                if (s.BotMaxSlippageBps <= 0)
                    deny(check, "a market order requires a non-zero slippage tolerance on the bot");
                break;

            case OrderType.Limit:
            case OrderType.StopLossLimit:
            case OrderType.TakeProfitLimit:
                if (s.LimitPrice is not { } limit || limit <= 0)
                    deny(check, $"a {s.OrderType} order requires a limit price greater than zero");
                else if (!InstrumentRules.IsOnGrid(limit, s.TickSize))
                    deny(check, $"limit price {limit} is not a multiple of the tick size {s.TickSize}");

                // Never defaulted: an unspecified time-in-force leaves the venue to choose how long
                // real money rests on the book.
                if (s.TimeInForce is null)
                    deny(check, $"a {s.OrderType} order requires an explicit time-in-force");
                break;

            case OrderType.StopLoss:
            case OrderType.TakeProfit:
                if (s.BotMaxSlippageBps <= 0)
                    deny(check, $"a {s.OrderType} order becomes a market order and requires a slippage bound");
                break;

            default:
                deny(check, $"order type {s.OrderType} is not one this platform is allowed to construct");
                break;
        }
    }

    private static void CheckNotional(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.NotionalWithinBounds;

        if (s.EstimatedNotional <= 0)
            deny(check, "the estimated notional must be greater than zero");

        if (s.VenueMinNotional > 0 && s.EstimatedNotional < s.VenueMinNotional)
            deny(check, $"notional {s.EstimatedNotional} is below the venue minimum {s.VenueMinNotional}");

        if (s.EffectiveMaxOrderNotional <= 0)
        {
            deny(check,
                "no per-order notional ceiling is configured; an unset limit denies rather than permits");
        }
        else if (s.EstimatedNotional > s.EffectiveMaxOrderNotional)
        {
            deny(check,
                $"notional {s.EstimatedNotional} exceeds the ceiling {s.EffectiveMaxOrderNotional}");
        }
    }

    private static void CheckExposure(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.ExposureWithinLimits;

        if (s.EffectiveMaxConcurrentPositions <= 0)
            deny(check, "no concurrent-position limit is configured; an unset limit denies");
        else if (s.OpenPositionCount >= s.EffectiveMaxConcurrentPositions)
            deny(check,
                $"{s.OpenPositionCount} position(s) are already open, at the limit of " +
                $"{s.EffectiveMaxConcurrentPositions}");

        var projected = s.OpenPositionNotional + s.EstimatedNotional;

        if (s.EffectiveMaxPositionNotional <= 0)
            deny(check, "no position notional ceiling is configured; an unset limit denies");
        else if (projected > s.EffectiveMaxPositionNotional)
            deny(check,
                $"resulting exposure {projected} exceeds the ceiling {s.EffectiveMaxPositionNotional}");
    }

    private static void CheckLossAndDrawdown(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.LossAndDrawdownWithinLimits;

        if (s.EffectiveMaxDailyLoss <= 0)
        {
            deny(check, "no daily loss limit is configured; an unset limit denies");
        }
        else
        {
            // Realised and unrealised are counted together. A bot that has lost its daily allowance on
            // paper but not yet closed the position has still lost it.
            var lossToday = -(s.RealizedPnlToday + s.OpenUnrealizedPnl);

            if (lossToday >= s.EffectiveMaxDailyLoss)
                deny(check, $"today's loss {lossToday} has reached the limit {s.EffectiveMaxDailyLoss}");
        }

        if (s.BotMaxDrawdown <= 0)
            deny(check, "the bot has no drawdown limit configured; an unset limit denies");
    }

    private static void CheckFrequency(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.FrequencyAndTurnoverWithinLimits;

        if (s.EffectiveMaxOrdersPerDay <= 0)
            deny(check, "no daily order limit is configured; an unset limit denies");
        else if (s.OrdersToday >= s.EffectiveMaxOrdersPerDay)
            deny(check,
                $"{s.OrdersToday} order(s) already submitted today, at the limit of " +
                $"{s.EffectiveMaxOrdersPerDay}");
    }

    private static void CheckBalance(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.SufficientBalance;

        if (s.AvailableQuoteBalance is not { } available)
        {
            deny(check, "the available balance is unknown, and an unknown balance is not a sufficient one");
            return;
        }

        // Only a buy spends quote currency. A sell is bounded by the base-asset position, which the
        // exposure check already covers.
        if (s.Side == OrderSide.Buy && available < s.EstimatedNotional)
            deny(check, $"available balance {available} is below the required notional {s.EstimatedNotional}");
    }

    private static void CheckConnectivity(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.ConnectivityAndReconciliationHealthy;

        // An unresolved ambiguous submission means the platform does not know its own position. Placing
        // another order on top of that is how one uncertain order becomes two real ones.
        if (s.UnresolvedAmbiguousIntents > 0)
            deny(check,
                $"{s.UnresolvedAmbiguousIntents} order intent(s) are unresolved; reconcile before trading");

        if (s.EffectiveMaxConsecutiveFailures <= 0)
            deny(check, "no consecutive-failure limit is configured; an unset limit denies");
        else if (s.ConsecutiveFailures >= s.EffectiveMaxConsecutiveFailures)
            deny(check,
                $"{s.ConsecutiveFailures} consecutive failures have reached the limit of " +
                $"{s.EffectiveMaxConsecutiveFailures}");
    }

    private static void CheckKillSwitches(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        if (s.EngagedKillSwitchScopes.Length > 0)
        {
            deny(RiskCheck.KillSwitchesClear,
                $"engaged: {string.Join("; ", s.EngagedKillSwitchScopes)}");
        }
    }

    private static void CheckHumanApproval(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        // Paper and sandbox need no approval — no real money is at stake. Live would, and the approval
        // workflow does not exist, so live denies here as well as in check 1.
        if (s.OperatingMode == OperatingMode.Live && !s.LiveExecutionAllowed)
        {
            deny(RiskCheck.HumanApprovalValid,
                "live orders require a human approval workflow that this platform does not implement");
        }
    }

    /// <summary>
    /// Check 16: the model's answer is usable as a sizing input — not extrapolated beyond the fitted
    /// barrier span, and at or above the bot's confidence floor.
    /// </summary>
    /// <remarks>
    /// Gates on the <c>BarrierExtrapolated</c> flag and never on the engine's warning prose. A
    /// percent-denominated bracket becomes a wide ATR bracket whenever the market is quiet, which is
    /// often, and sizing on an extrapolated expected value is sizing on an artefact rather than a
    /// measurement.
    /// </remarks>
    private static void CheckModelOutputUsable(RiskSnapshot s, Action<RiskCheck, string> deny)
    {
        const RiskCheck check = RiskCheck.BarrierWithinFittedRange;

        if (s.BarrierExtrapolated)
        {
            deny(check,
                "the requested barrier fell outside the model's fitted ATR span, making its expected " +
                "value an extrapolation");
        }

        if (s.BotMinimumConfidence > 0 && s.Confidence < s.BotMinimumConfidence)
        {
            deny(check,
                $"confidence {s.Confidence:F4} is below the bot's floor {s.BotMinimumConfidence:F4}");
        }
    }
}
