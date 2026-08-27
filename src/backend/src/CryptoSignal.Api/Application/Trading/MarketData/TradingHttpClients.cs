using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.MarketData;

/// <summary>
/// Names of the configured <see cref="IHttpClientFactory"/> clients, one per reachable venue.
/// </summary>
/// <remarks>
/// Named rather than typed clients because the base address, timeout and proxy belong to the
/// <em>venue</em>, while several unrelated types talk to it — the kline source, the instrument-rule
/// provider and the broker all address the same host and must share its configuration. Mapping
/// venue → client name in one place is what keeps a sandbox broker from ever borrowing the mainnet
/// channel.
/// </remarks>
public static class TradingHttpClients
{
    public const string BinanceTestnet = "binance-testnet";
    public const string BinanceMainnet = "binance-mainnet";
    public const string Bitunix = "bitunix";
    public const string Bybit = "bybit";

    /// <summary>The client name for a venue, or throws for a venue that speaks no HTTP.</summary>
    public static string ForVenue(MarketVenue venue) => venue switch
    {
        MarketVenue.BinanceTestnet => BinanceTestnet,
        MarketVenue.BinanceMainnet => BinanceMainnet,
        MarketVenue.Bitunix => Bitunix,
        MarketVenue.Bybit => Bybit,
        _ => throw new ArgumentOutOfRangeException(
            nameof(venue), venue, $"{venue} is not an HTTP venue; it has no configured client."),
    };
}
