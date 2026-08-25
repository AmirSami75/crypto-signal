using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Risk;

/// <summary>
/// Every fact the checks are allowed to consult, read once, at one moment, before any check runs.
/// </summary>
/// <remarks>
/// <para>
/// This type exists to make a specific bug impossible. If check 9 counted open positions and check 12
/// then re-read the balance, a fill landing between them would let one order be measured against two
/// different portfolios — and the pair of checks could both pass on states that never coexisted. So the
/// snapshot is taken once and the checks are pure functions of it.
/// </para>
/// <para>
/// It is also the audit artefact: serialised into <c>RiskDecisions.SnapshotJson</c> so a post-mortem
/// queries the numbers the checks actually saw rather than reconstructing them from prices that have
/// since moved. That is why the effective limits are recorded alongside the raw ones — "denied because
/// the platform ceiling was tighter than the bot's" is a different finding from "denied because the bot
/// was misconfigured", and only the resolved pair distinguishes them.
/// </para>
/// </remarks>
public sealed record RiskSnapshot
{
    /// <summary>When the snapshot was taken. Every age in it is measured from here.</summary>
    public DateTime TakenAt { get; init; }

    #region Subject

    public Guid BotId { get; init; }
    public string BotName { get; init; } = string.Empty;
    public BotStatus BotStatus { get; init; }
    public OperatingMode OperatingMode { get; init; }
    public MarketVenue Venue { get; init; }
    public string Symbol { get; init; } = string.Empty;
    public string Interval { get; init; } = string.Empty;

    public Guid StrategyDecisionId { get; init; }
    public Guid OrderIntentId { get; init; }
    public string ClientOrderId { get; init; } = string.Empty;
    public TradeDirection Direction { get; init; }
    public OrderSide Side { get; init; }
    public OrderType OrderType { get; init; }
    public TimeInForce? TimeInForce { get; init; }
    public decimal Quantity { get; init; }
    public decimal? LimitPrice { get; init; }
    public decimal ReferencePrice { get; init; }
    public decimal EstimatedNotional { get; init; }

    #endregion

    #region Engine provenance

    public string ModelId { get; init; } = string.Empty;
    public string ModelVersion { get; init; } = string.Empty;
    public string? BotExpectedModelVersion { get; init; }
    public bool BarrierExtrapolated { get; init; }
    public bool UsedWildcardModel { get; init; }
    public double Confidence { get; init; }
    public double ExpectedValue { get; init; }
    public DateTime DecisionCandleOpenTime { get; init; }
    public DateTime? DecisionValidUntil { get; init; }
    public string DecisionSymbol { get; init; } = string.Empty;
    public string DecisionInterval { get; init; } = string.Empty;
    public OperatingMode DecisionOperatingMode { get; init; }
    public Guid DecisionBotId { get; init; }

    #endregion

    #region Freshness

    public DateTime NewestCandleOpenTime { get; init; }
    public double CandleAgeSeconds { get; init; }
    public double IntervalSeconds { get; init; }
    public double MaxCandleAgeSeconds { get; init; }

    #endregion

    #region Venue filters

    public bool InstrumentTradable { get; init; }
    public bool VenueSupportsMarketOrders { get; init; }
    public decimal TickSize { get; init; }
    public decimal StepSize { get; init; }
    public decimal MinQuantity { get; init; }
    public decimal MaxQuantity { get; init; }
    public decimal VenueMinNotional { get; init; }

    #endregion

    #region Portfolio, as of TakenAt

    public int OpenPositionCount { get; init; }
    public decimal OpenPositionNotional { get; init; }
    public bool HasOpenPositionForSymbol { get; init; }
    public int OrdersToday { get; init; }
    public decimal RealizedPnlToday { get; init; }
    public decimal OpenUnrealizedPnl { get; init; }
    public decimal? AvailableQuoteBalance { get; init; }

    #endregion

    #region Health

    public int ConsecutiveFailures { get; init; }
    public int UnresolvedAmbiguousIntents { get; init; }

    /// <summary>True when this decision already produced an intent other than the one being evaluated.</summary>
    public bool DecisionAlreadyActedOn { get; init; }

    /// <summary>Scopes of every engaged kill switch that covers this bot. Empty is the only clear state.</summary>
    public string[] EngagedKillSwitchScopes { get; init; } = [];

    #endregion

    #region Effective limits (min of bot and platform; 0 denies)

    public bool LiveExecutionAllowed { get; init; }
    public bool ModeEnabled { get; init; }
    public bool SymbolAllowlisted { get; init; }
    public bool ShortingAllowed { get; init; }
    public bool SpotOnly { get; init; }
    public bool ModelVersionApproved { get; init; }

    public decimal EffectiveMaxOrderNotional { get; init; }
    public decimal EffectiveMaxPositionNotional { get; init; }
    public decimal EffectiveMaxDailyLoss { get; init; }
    public int EffectiveMaxOrdersPerDay { get; init; }
    public int EffectiveMaxConcurrentPositions { get; init; }
    public int EffectiveMaxConsecutiveFailures { get; init; }
    public decimal BotMaxDrawdown { get; init; }
    public int BotMaxSlippageBps { get; init; }
    public double BotMinimumConfidence { get; init; }

    #endregion
}
