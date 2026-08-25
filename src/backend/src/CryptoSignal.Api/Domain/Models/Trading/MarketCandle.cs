using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// One closed candle as a named venue reported it, recorded so any decision can be replayed against
/// the exact prices that produced it.
/// </summary>
/// <remarks>
/// <para>
/// Keyed by <c>(venue, symbol, interval, openTime)</c> and deliberately <b>not</b> by operating mode.
/// A candle is a fact about a venue, not about a portfolio: paper and sandbox both read the testnet,
/// and storing the same candle once per mode would invite the two copies to disagree about a price
/// that has only one true value. Mode isolation belongs on records that represent money — positions,
/// intents, fills — not on market history.
/// </para>
/// <para>
/// Only closed candles are stored. <see cref="IsClosed"/> exists to make that explicit at the row
/// level rather than implicit in the writer, because an in-progress candle leaks future information
/// into the features and invalidates every decision computed from it.
/// </para>
/// </remarks>
public class MarketCandle : BaseEntity
{
    /// <summary>Which venue reported this candle.</summary>
    public MarketVenue Venue { get; set; }

    /// <summary>Exchange symbol, uppercase.</summary>
    public string Symbol { get; set; } = string.Empty;

    /// <summary>Candle interval, e.g. <c>1h</c>.</summary>
    public string Interval { get; set; } = string.Empty;

    /// <summary>Candle open time, UTC. The candle's identity.</summary>
    public DateTime OpenTime { get; set; }

    /// <summary>Candle close time, UTC.</summary>
    public DateTime CloseTime { get; set; }

    public decimal Open { get; set; }
    public decimal High { get; set; }
    public decimal Low { get; set; }
    public decimal Close { get; set; }

    /// <summary>Base-asset volume.</summary>
    public decimal Volume { get; set; }

    /// <summary>Quote-asset volume, when the venue reports it.</summary>
    public decimal? QuoteVolume { get; set; }

    /// <summary>Trades in the candle, when the venue reports it.</summary>
    public int? TradeCount { get; set; }

    /// <summary>True only for a candle the venue has closed. Always true for stored rows.</summary>
    public bool IsClosed { get; set; } = true;

    /// <summary>When this platform received the candle. Distinct from <see cref="OpenTime"/>.</summary>
    public DateTime FetchedAt { get; set; }
}
