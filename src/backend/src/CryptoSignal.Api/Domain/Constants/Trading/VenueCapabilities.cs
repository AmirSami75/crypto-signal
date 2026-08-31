using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Domain.Constants.Trading;

/// <summary>
/// Venue capabilities in one place. Every "is this venue a futures market?" decision in the
/// codebase reads from here, because a per-call-site enum comparison is how <c>BinanceFuturesTestnet</c>
/// shipped without the start gate knowing it: the bot saved, then refused to start with
/// "leverage must be 1 for spot markets" — a contradiction only visible in production.
/// </summary>
public static class VenueCapabilities
{
    /// <summary>Venues where positions are margined contracts: leverage is meaningful and shorts borrow.</summary>
    public static readonly IReadOnlySet<MarketVenue> FuturesVenues = new HashSet<MarketVenue>
    {
        MarketVenue.Bybit,
        MarketVenue.BinanceFuturesTestnet,
    };

    /// <summary>True when the venue prices margined contracts rather than spot balances.</summary>
    public static bool IsFutures(this MarketVenue venue) => FuturesVenues.Contains(venue);
}
