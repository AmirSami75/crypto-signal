using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.DTOs.Trading;

/// <summary>
/// A bot's writable configuration. Every field here is configuration; none of it is state.
/// </summary>
/// <remarks>
/// <para>
/// The risk limits are part of the same payload as the bet on purpose. They are not advanced settings
/// hidden behind a toggle: a bot with untouched limits cannot trade, because <b>a zero limit denies and
/// never means unlimited</b> (<c>docs/LIVE_TRADING_SAFETY.md</c>). Presenting them alongside the notional
/// makes that visible at the moment someone decides how much to commit.
/// </para>
/// <para>
/// <see cref="OperatingMode"/> is fixed once the bot exists and cannot be edited afterwards. Flipping a
/// running bot between paper and sandbox would leave one position history spanning two venues, and the
/// P&amp;L series would describe a portfolio that never existed.
/// </para>
/// </remarks>
public sealed record BotInputDto
{
    public string Name { get; init; } = string.Empty;

    public string? Description { get; init; }

    public string Symbol { get; init; } = string.Empty;

    public string Interval { get; init; } = string.Empty;

    public MarketVenue Venue { get; init; }

    /// <summary>
    /// Optional credential pin. Must name an active connection owned by the caller; null resolves the
    /// operator's environment credentials at tick time.
    /// </summary>
    public Guid? ExchangeConnectionId { get; init; }

    /// <summary>Ignored on update — the mode is fixed for the bot's lifetime.</summary>
    public OperatingMode OperatingMode { get; init; } = OperatingMode.Paper;

    public decimal TakeProfitPercent { get; init; }

    public decimal StopLossPercent { get; init; }

    public bool AllowShort { get; init; }

    /// <summary>Requested futures leverage. Must be 1 on spot/replay venues.</summary>
    public int Leverage { get; init; } = 1;

    public decimal QuoteNotionalPerTrade { get; init; }

    public double MinimumConfidence { get; init; }

    public int MaxHoldingPeriods { get; init; }

    public int CadenceSeconds { get; init; } = 60;

    #region Risk limits — every one of these denies at zero

    public decimal MaxOrderNotional { get; init; }

    public decimal MaxPositionNotional { get; init; }

    public decimal MaxDailyLoss { get; init; }

    public decimal MaxDrawdown { get; init; }

    public int MaxConcurrentPositions { get; init; }

    public int MaxOrdersPerDay { get; init; }

    public int MaxConsecutiveFailures { get; init; }

    public int MaxSlippageBps { get; init; }

    #endregion

    /// <summary>
    /// Model version this bot requires, or null to accept whatever the engine serves. Pinning it makes
    /// the engine refuse after a retrain, which is the point: a bot whose limits were tuned against one
    /// model should stop rather than silently inherit another.
    /// </summary>
    public string? ExpectedModelVersion { get; init; }
}

/// <summary>Reason accompanying a lifecycle change. Required — an unexplained halt is not auditable.</summary>
public sealed record BotStatusChangeDto
{
    public string Reason { get; init; } = string.Empty;
}

/// <summary>An open or recently closed position as the bot's own records describe it.</summary>
public sealed record BotPositionDto(
    Guid Id,
    OperatingMode OperatingMode,
    MarketVenue Venue,
    string Symbol,
    TradeDirection Direction,
    PositionStatus Status,
    decimal AverageEntryPrice,
    decimal Quantity,
    decimal EntryNotional,
    decimal? TakeProfitPrice,
    decimal? StopLossPrice,
    DateTime OpenedAt,
    DateTime? ClosedAt,
    int BarsHeld,
    decimal? AverageExitPrice,
    PositionCloseReason? CloseReason,
    decimal RealizedPnl,
    decimal FeesPaid,
    decimal? UnrealizedPnl,
    decimal? LastMarkPrice,
    DateTime? LastMarkedAt,
    decimal MaxAdverseExcursion);

/// <summary>The scheduler's lease and counters for a bot. Operator diagnostics, not trading state.</summary>
public sealed record BotRunDto(
    Guid Id,
    string LeaseOwner,
    DateTime StartedAt,
    DateTime LastHeartbeatAt,
    DateTime? EndedAt,
    long TickCount,
    long DecisionCount,
    long OrderCount,
    long ErrorCount,
    int ConsecutiveFailureCount,
    string? LastError,
    DateTime? LastErrorAt,
    DateTime? LastTickAt);

/// <summary>One row in the bot listing.</summary>
public sealed record BotSummaryDto
{
    public Guid Id { get; init; }
    public string Name { get; init; } = string.Empty;
    public string Symbol { get; init; } = string.Empty;
    public string Interval { get; init; } = string.Empty;
    public MarketVenue Venue { get; init; }
    public OperatingMode OperatingMode { get; init; }
    public BotStatus Status { get; init; }
    public string? StatusReason { get; init; }
    public decimal TakeProfitPercent { get; init; }
    public decimal StopLossPercent { get; init; }
    public bool AllowShort { get; init; }
    public int Leverage { get; init; } = 1;
    public decimal QuoteNotionalPerTrade { get; init; }
    public int CadenceSeconds { get; init; }
    public DateTime? LastTickAt { get; init; }
    public DateTime? LastEvaluatedCandleOpenTime { get; init; }
    public DateTime? FaultedAt { get; init; }
    public DateTime CreatedAt { get; init; }

    /// <summary>Positions currently open, counted within this bot's own operating mode.</summary>
    public int OpenPositionCount { get; init; }

    /// <summary>Realised P&amp;L across this bot's closed positions, in quote currency.</summary>
    public decimal RealizedPnl { get; init; }

    /// <summary>
    /// True when a kill switch covering this bot is engaged. The bot's own status can read
    /// <c>Active</c> while this is true; the switch blocks new intents without changing the status,
    /// so both have to be shown or an operator sees "Active" and assumes it is trading.
    /// </summary>
    public bool IsBlockedByKillSwitch { get; init; }
}

/// <summary>A bot's full configuration, current status, lease and open positions.</summary>
public sealed record BotDetailDto
{
    public Guid Id { get; init; }
    public string Name { get; init; } = string.Empty;
    public string? Description { get; init; }
    public string Symbol { get; init; } = string.Empty;
    public string Interval { get; init; } = string.Empty;
    public MarketVenue Venue { get; init; }
    public OperatingMode OperatingMode { get; init; }

    public decimal TakeProfitPercent { get; init; }
    public decimal StopLossPercent { get; init; }
    public bool AllowShort { get; init; }
    public int Leverage { get; init; } = 1;
    public decimal QuoteNotionalPerTrade { get; init; }
    public double MinimumConfidence { get; init; }
    public int MaxHoldingPeriods { get; init; }
    public int CadenceSeconds { get; init; }

    public BotStatus Status { get; init; }
    public string? StatusReason { get; init; }
    public DateTime? FaultedAt { get; init; }
    public DateTime? LastEvaluatedCandleOpenTime { get; init; }
    public DateTime? LastTickAt { get; init; }

    public decimal MaxOrderNotional { get; init; }
    public decimal MaxPositionNotional { get; init; }
    public decimal MaxDailyLoss { get; init; }
    public decimal MaxDrawdown { get; init; }
    public int MaxConcurrentPositions { get; init; }
    public int MaxOrdersPerDay { get; init; }
    public int MaxConsecutiveFailures { get; init; }
    public int MaxSlippageBps { get; init; }

    public string? ExpectedModelVersion { get; init; }

    public Guid? ExchangeConnectionId { get; init; }

    public DateTime CreatedAt { get; init; }
    public DateTime? UpdatedAt { get; init; }

    /// <summary>Latest scheduler lease, or null if the bot has never been started.</summary>
    public BotRunDto? CurrentRun { get; init; }

    /// <summary>Positions still open. Filtered to this bot's operating mode by construction.</summary>
    public IReadOnlyList<BotPositionDto> OpenPositions { get; init; } = [];

    public decimal RealizedPnl { get; init; }

    public int ClosedPositionCount { get; init; }

    public bool IsBlockedByKillSwitch { get; init; }
}
