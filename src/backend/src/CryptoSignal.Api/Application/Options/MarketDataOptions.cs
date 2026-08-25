using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Options;

/// <summary>Market-data settings that are not venue credentials. Bound from <c>MarketData</c>.</summary>
public sealed class MarketDataOptions
{
    public const string SectionName = "MarketData";

    /// <summary>
    /// Directory holding the recorded <c>&lt;SYMBOL&gt;_&lt;interval&gt;.csv</c> files the replay source
    /// reads. Empty is not a default path — the replay source throws instead, because guessing a
    /// directory is how a test silently reads the wrong fixture.
    /// </summary>
    public string ReplayDataDirectory { get; init; } = string.Empty;

    /// <summary>
    /// Venue the on-demand signal endpoint reads candles from when the caller does not name one.
    /// </summary>
    /// <remarks>
    /// Defaults to the Binance testnet because that is the venue reachable from inside the container
    /// network, and because it is also the sandbox execution venue — candles and fills then come from one
    /// consistent market rather than from two that disagree. A default is safe here in a way it is not
    /// for a risk limit: naming the wrong venue produces a visibly wrong answer, and the endpoint places
    /// nothing either way.
    /// </remarks>
    public MarketVenue SignalVenue { get; init; } = MarketVenue.BinanceTestnet;
}
