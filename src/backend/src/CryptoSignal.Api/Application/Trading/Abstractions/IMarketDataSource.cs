using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Abstractions;

/// <summary>A venue that can be asked for closed candles.</summary>
/// <remarks>
/// <para>
/// Implementations return <b>closed candles only</b>, oldest first. The in-progress candle is excluded
/// deliberately: its high, low and close are still moving, so feeding it to the model leaks future
/// information into the features and invalidates the answer.
/// </para>
/// <para>
/// A source that cannot produce the requested window must throw, never return a short or padded one.
/// The bot faults instead — silently substituting another venue's prices, or trading on a gap, is the
/// "missing data as permission to trade" antipattern the safety policy prohibits. There is no fallback
/// chain anywhere in this interface's implementations by design.
/// </para>
/// </remarks>
public interface IMarketDataSource
{
    MarketVenue Venue { get; }

    /// <summary>The most recent <paramref name="count"/> closed candles, oldest first.</summary>
    Task<IReadOnlyList<MarketCandleData>> GetClosedCandlesAsync(
        string symbol,
        string interval,
        int count,
        CancellationToken cancellationToken);
}

/// <summary>Picks the source for a venue. Explicit selection only — a miss is an error, not a default.</summary>
public interface IMarketDataSourceResolver
{
    IMarketDataSource Resolve(MarketVenue venue);
}
