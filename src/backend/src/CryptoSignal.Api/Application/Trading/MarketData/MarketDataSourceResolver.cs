using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.MarketData;

/// <summary>
/// Picks the candle source for a venue. One venue, one source, no chain.
/// </summary>
/// <remarks>
/// <para>
/// The absence of a fallback is the design. A resolver that tried the next source when one failed would be
/// substituting a different venue's prices into a decision, and the record would still say the bot's own
/// venue — precisely the antipattern <c>LIVE_TRADING_SAFETY.md</c> prohibits. An unresolvable or failing
/// venue faults the bot instead, and the fault names the venue.
/// </para>
/// <para>
/// Two sources claiming one venue is a wiring bug, not a preference to be resolved by ordering, so it
/// throws at resolve time naming both. The check is here rather than in a constructor because DI builds
/// this per scope and a startup assertion would only relocate the same message.
/// </para>
/// </remarks>
public sealed class MarketDataSourceResolver(IEnumerable<IMarketDataSource> sources)
    : IMarketDataSourceResolver, IScopedSvcMarker
{
    public IMarketDataSource Resolve(MarketVenue venue)
    {
        IMarketDataSource? found = null;

        foreach (var source in sources)
        {
            if (source.Venue != venue)
                continue;

            if (found is not null)
            {
                throw new InvalidOperationException(
                    $"Both {found.GetType().Name} and {source.GetType().Name} claim venue {venue}. " +
                    "Which one answers cannot be decided by registration order.");
            }

            found = source;
        }

        return found ?? throw new InvalidOperationException(
            $"No market-data source is registered for venue {venue}. Registered venues: " +
            $"{string.Join(", ", sources.Select(s => s.Venue.ToString()).Distinct().Order(StringComparer.Ordinal))}. " +
            "There is no fallback venue by design.");
    }
}
