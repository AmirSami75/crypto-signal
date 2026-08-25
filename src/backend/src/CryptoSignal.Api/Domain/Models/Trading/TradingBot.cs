using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// A configured bot: one market, one bet shape, one set of limits. This is configuration only — it
/// holds no position and no money. What the bot has actually done lives in <see cref="BotPosition"/>,
/// <see cref="OrderIntent"/> and the audit chain.
/// </summary>
/// <remarks>
/// <para>
/// Every limit on this entity is a <b>deny</b> threshold, and every one of them denies at zero. The
/// safety policy is explicit that a zero or missing limit denies the action and never means unlimited,
/// so a freshly created bot with untouched limits cannot trade until an operator sets them — which is
/// the intended failure mode, not an inconvenience to work around.
/// </para>
/// <para>
/// <see cref="OperatingMode"/> is fixed per bot rather than toggled at run time. Flipping a live bot to
/// paper and back would leave one position history spanning two venues, and the resulting P&amp;L series
/// would describe a portfolio that never existed.
/// </para>
/// </remarks>
public class TradingBot : BaseEntity
{
    #region Identity

    /// <summary>Operator-facing name. Not an identifier.</summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>Free-text note about the bot's purpose.</summary>
    public string? Description { get; set; }

    #endregion

    #region Market

    /// <summary>Exchange symbol, e.g. <c>BTCUSDT</c>. Uppercase, as the venue spells it.</summary>
    public string Symbol { get; set; } = string.Empty;

    /// <summary>Candle interval, e.g. <c>1h</c>. Must be one the engine has a model for.</summary>
    public string Interval { get; set; } = string.Empty;

    /// <summary>Which venue supplies candles and receives orders.</summary>
    public MarketVenue Venue { get; set; }

    /// <summary>Which venue class this bot's records belong to. Fixed for the bot's lifetime.</summary>
    public OperatingMode OperatingMode { get; set; } = OperatingMode.Paper;

    #endregion

    #region The bet

    /// <summary>Take-profit distance as a percent of entry price. Greater than zero.</summary>
    public decimal TakeProfitPercent { get; set; }

    /// <summary>Stop-loss distance as a percent of entry price. Greater than zero.</summary>
    public decimal StopLossPercent { get; set; }

    /// <summary>
    /// Whether a short-side edge may be acted on. False still records the short confidence — the bot
    /// can be shown the edge it declined — it only stops the direction from being SHORT.
    /// </summary>
    public bool AllowShort { get; set; }

    /// <summary>Quote-currency notional committed per entry, e.g. 100 USDT.</summary>
    public decimal QuoteNotionalPerTrade { get; set; }

    /// <summary>Calibrated confidence floor. Below it the bot stands down.</summary>
    public double MinimumConfidence { get; set; }

    /// <summary>Candles after which an unresolved position is abandoned. Zero uses the engine default.</summary>
    public int MaxHoldingPeriods { get; set; }

    #endregion

    #region Scheduling

    /// <summary>How often the scheduler evaluates this bot, in seconds.</summary>
    public int CadenceSeconds { get; set; } = 60;

    /// <summary>Lifecycle state. Only <see cref="BotStatus.Active"/> is scheduled.</summary>
    public BotStatus Status { get; set; } = BotStatus.Draft;

    /// <summary>Why the bot is in its current status, when the status needs explaining.</summary>
    public string? StatusReason { get; set; }

    /// <summary>When the bot faulted, if it did.</summary>
    public DateTime? FaultedAt { get; set; }

    /// <summary>
    /// Open time of the last candle this bot decided on. The scheduler compares against it so a
    /// re-delivered tick for the same candle does no work.
    /// </summary>
    public DateTime? LastEvaluatedCandleOpenTime { get; set; }

    /// <summary>When the bot last completed a tick, successfully or not.</summary>
    public DateTime? LastTickAt { get; set; }

    #endregion

    #region Risk limits

    /// <summary>Largest notional a single order may carry. Zero denies.</summary>
    public decimal MaxOrderNotional { get; set; }

    /// <summary>Largest notional this bot may hold in one position. Zero denies.</summary>
    public decimal MaxPositionNotional { get; set; }

    /// <summary>Realized plus unrealized loss over a rolling day that halts the bot. Zero denies.</summary>
    public decimal MaxDailyLoss { get; set; }

    /// <summary>Peak-to-trough equity decline that halts the bot. Zero denies.</summary>
    public decimal MaxDrawdown { get; set; }

    /// <summary>Positions this bot may hold at once. Zero denies.</summary>
    public int MaxConcurrentPositions { get; set; }

    /// <summary>Orders this bot may place in a rolling day. Zero denies.</summary>
    public int MaxOrdersPerDay { get; set; }

    /// <summary>Consecutive rejected or failed orders after which the bot faults. Zero denies.</summary>
    public int MaxConsecutiveFailures { get; set; }

    /// <summary>
    /// Tolerated deviation between the reference price a decision used and the price at submission, in
    /// basis points. Also the paper broker's simulated slippage. Zero denies.
    /// </summary>
    public int MaxSlippageBps { get; set; }

    #endregion

    #region Model pinning

    /// <summary>
    /// Model version this bot requires, or null to accept whatever the engine currently serves. Set it
    /// and the engine refuses to answer after a retrain, which is the point: a bot whose limits were
    /// tuned against one model should stop rather than silently inherit another.
    /// </summary>
    public string? ExpectedModelVersion { get; set; }

    #endregion
}
