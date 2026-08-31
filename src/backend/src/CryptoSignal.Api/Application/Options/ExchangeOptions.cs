using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Options;

/// <summary>
/// Where the exchange venues live and, for the sandbox, what credentials reach them. Bound from
/// <c>Exchange</c>.
/// </summary>
/// <remarks>
/// <para>
/// <b>Credentials are supplied by environment variables only</b> —
/// <c>Exchange__BinanceTestnet__ApiKey</c> and <c>Exchange__BinanceTestnet__ApiSecret</c> — and are never
/// committed, never logged, and never placed in a response body. The key reaches exactly one place: the
/// <c>X-MBX-APIKEY</c> header of a signed request. The secret reaches exactly one: the HMAC.
/// </para>
/// <para>
/// The two base addresses have compile-time defaults (<see cref="BinanceEndpoints"/>) rather than
/// required config, so a deployment that configures nothing still points at the right hosts. That is not
/// a fail-open: an endpoint address is not a permission, and no order can be placed against either host
/// without credentials the operator supplied and a risk verdict that allowed it.
/// </para>
/// </remarks>
public sealed class ExchangeOptions
{
    public const string SectionName = "Exchange";

    public BinanceVenueOptions BinanceTestnet { get; init; } = new();

    public BinanceVenueOptions BinanceMainnet { get; init; } = new();

    public BinanceVenueOptions BinanceFuturesTestnet { get; init; } = new();

    public BinanceVenueOptions Bitunix { get; init; } = new();

    public BinanceVenueOptions Bybit { get; init; } = new();

    /// <summary>
    /// How long a signed request stays valid at the venue, in milliseconds. Binance rejects anything
    /// older, which is what stops a replayed request from executing late.
    /// </summary>
    public int RecvWindowMs { get; init; } = 5_000;

    /// <summary>Per-request HTTP timeout. A timeout on a write is an ambiguous outcome, never a failure.</summary>
    public int RequestTimeoutSeconds { get; init; } = 15;

    /// <summary>The venue's REST root: the configured value, or the well-known default when unset.</summary>
    public string RestBaseUrl(MarketVenue venue) => venue switch
    {
        MarketVenue.BinanceTestnet => Or(BinanceTestnet.RestBaseUrl, BinanceEndpoints.BinanceTestnet),
        MarketVenue.BinanceFuturesTestnet => Or(BinanceFuturesTestnet.RestBaseUrl, BinanceEndpoints.BinanceFuturesTestnet),
        MarketVenue.BinanceMainnet => Or(BinanceMainnet.RestBaseUrl, BinanceEndpoints.BinanceMainnet),
        MarketVenue.Bitunix => Or(Bitunix.RestBaseUrl, BinanceEndpoints.Bitunix),
        MarketVenue.Bybit => Or(Bybit.RestBaseUrl, BinanceEndpoints.BybitDemo),
        _ => throw new ArgumentOutOfRangeException(
            nameof(venue), venue, "This venue has no REST endpoint configured here."),
    };

    public BinanceVenueOptions For(MarketVenue venue) => venue switch
    {
        MarketVenue.BinanceTestnet => BinanceTestnet,
        MarketVenue.BinanceFuturesTestnet => BinanceFuturesTestnet,
        MarketVenue.BinanceMainnet => BinanceMainnet,
        MarketVenue.Bitunix => Bitunix,
        MarketVenue.Bybit => Bybit,
        _ => throw new ArgumentOutOfRangeException(
            nameof(venue), venue, "This venue is not configured here."),
    };

    private static string Or(string? configured, string fallback) =>
        string.IsNullOrWhiteSpace(configured) ? fallback : configured.TrimEnd('/');
}

/// <summary>One Binance-compatible venue.</summary>
public sealed class BinanceVenueOptions
{
    /// <summary>REST root, e.g. <c>https://testnet.binance.vision</c>. Empty uses the built-in default.</summary>
    public string RestBaseUrl { get; init; } = string.Empty;

    /// <summary>Environment-supplied. Empty means this venue cannot be traded, and asking it to is an error.</summary>
    public string ApiKey { get; init; } = string.Empty;

    /// <summary>Environment-supplied. Never logged, never hashed into an audit row, never returned.</summary>
    public string ApiSecret { get; init; } = string.Empty;

    /// <summary>
    /// Optional forward proxy. Mainnet is not reachable from inside the compose network, so a host-side
    /// proxy is the only way to reach it; the testnet needs none.
    /// </summary>
    public string ProxyUrl { get; init; } = string.Empty;

    public bool HasCredentials =>
        !string.IsNullOrWhiteSpace(ApiKey) && !string.IsNullOrWhiteSpace(ApiSecret);
}

/// <summary>Well-known REST roots, so an unconfigured deployment still points somewhere real.</summary>
public static class BinanceEndpoints
{
    public const string BinanceTestnet = "https://testnet.binance.vision";
    public const string BinanceMainnet = "https://api.binance.com";
    public const string BinanceFuturesTestnet = "https://testnet.binancefuture.com";

    /// <summary>Bitunix's OpenAPI host (futures).</summary>
    public const string Bitunix = "https://fapi.bitunix.com";

    /// <summary>Bybit's v5 demo-trading host (futures, virtual funds).</summary>
    public const string BybitDemo = "https://api-demo.bybit.com";
}
