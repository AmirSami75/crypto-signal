using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// A position a bot holds or held: the exposure, the bracket protecting it, and what it cost or made.
/// This — not the ML engine — is where position state lives; the engine is stateless and is told about
/// the position on every request.
/// </summary>
/// <remarks>
/// <para>
/// Every money column is <c>decimal</c>, and P&amp;L is accumulated from recorded fills rather than
/// recomputed from prices at read time. Two reads of the same closed position must not be able to
/// disagree about what it earned, which they would if the figure were derived from a live mark.
/// </para>
/// <para>
/// <see cref="UnrealizedPnl"/> is the one exception and is explicitly a snapshot: it is only meaningful
/// alongside <see cref="LastMarkedAt"/>, and a consumer that reads it without checking that timestamp
/// is reading a number whose age it does not know.
/// </para>
/// </remarks>
public class BotPosition : BaseEntity
{
    #region Identity

    public Guid BotId { get; set; }

    /// <summary>Which venue class this position belongs to. Filtered on every read.</summary>
    public OperatingMode OperatingMode { get; set; }

    public MarketVenue Venue { get; set; }

    public string Symbol { get; set; } = string.Empty;

    public TradeDirection Direction { get; set; }

    public PositionStatus Status { get; set; } = PositionStatus.Open;

    #endregion

    #region Exposure

    /// <summary>Quantity-weighted average entry price, from fills.</summary>
    public decimal AverageEntryPrice { get; set; }

    /// <summary>Base-asset quantity currently held. Zero once closed.</summary>
    public decimal Quantity { get; set; }

    /// <summary>Quote notional committed at entry.</summary>
    public decimal EntryNotional { get; set; }

    /// <summary>Take-profit price working at the venue, when there is one.</summary>
    public decimal? TakeProfitPrice { get; set; }

    /// <summary>Stop-loss price working at the venue, when there is one.</summary>
    public decimal? StopLossPrice { get; set; }

    #endregion

    #region Lifecycle

    /// <summary>The intent that opened it.</summary>
    public Guid? OpenedByOrderIntentId { get; set; }

    /// <summary>The intent that closed it.</summary>
    public Guid? ClosedByOrderIntentId { get; set; }

    /// <summary>Open time of the candle the opening decision was made on.</summary>
    public DateTime OpenedFromCandleOpenTime { get; set; }

    public DateTime OpenedAt { get; set; }

    public DateTime? ClosedAt { get; set; }

    /// <summary>Closed candles elapsed since opening. Fed to the engine on every request.</summary>
    public int BarsHeld { get; set; }

    /// <summary>Quantity-weighted average exit price, from fills.</summary>
    public decimal? AverageExitPrice { get; set; }

    /// <summary>Why the position ended.</summary>
    public PositionCloseReason? CloseReason { get; set; }

    #endregion

    #region Result

    /// <summary>Realized P&amp;L, net of recorded fees. Accumulated from fills.</summary>
    public decimal RealizedPnl { get; set; }

    /// <summary>Fees paid across every fill, in quote terms.</summary>
    public decimal FeesPaid { get; set; }

    /// <summary>Unrealized P&amp;L as of <see cref="LastMarkedAt"/>. Meaningless without it.</summary>
    public decimal? UnrealizedPnl { get; set; }

    /// <summary>Price the position was last marked at.</summary>
    public decimal? LastMarkPrice { get; set; }

    /// <summary>When the position was last marked.</summary>
    public DateTime? LastMarkedAt { get; set; }

    /// <summary>Worst adverse excursion seen while open, in quote terms. Risk observability.</summary>
    public decimal MaxAdverseExcursion { get; set; }

    #endregion
}
