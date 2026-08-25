using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Brokers;

/// <summary>
/// Picks the broker for a (mode, venue) pair. Exactly one may claim it.
/// </summary>
/// <remarks>
/// <para>
/// Both halves of the key matter. Mode alone would let a SANDBOX bot be served by whichever venue adapter
/// happened to be registered first; venue alone would let a PAPER bot reach a real one. Each broker answers
/// <see cref="IBroker.Supports"/> for itself, so adding a venue cannot silently widen an existing one.
/// </para>
/// <para>
/// <b>LIVE resolves to nothing, on purpose.</b> No registered broker claims it, so a bot configured for live
/// execution fails to resolve and faults with the message below rather than falling through to a simulator
/// and reporting paper fills as real ones. Gates 6-8 of <c>LIVE_TRADING_SAFETY.md</c> are unimplemented, and
/// this is where that shows up as behaviour instead of a comment.
/// </para>
/// </remarks>
public sealed class BrokerResolver(IEnumerable<IBroker> brokers) : IBrokerResolver, IScopedSvcMarker
{
    public IBroker Resolve(OperatingMode mode, MarketVenue venue)
    {
        IBroker? found = null;

        foreach (var broker in brokers)
        {
            if (!broker.Supports(mode, venue))
                continue;

            if (found is not null)
            {
                throw new InvalidOperationException(
                    $"Both {found.Name} and {broker.Name} claim {mode} on {venue}. Which one places the " +
                    "order cannot be decided by registration order.");
            }

            found = broker;
        }

        if (found is not null)
            return found;

        var registered = brokers.Select(b => b.Name).Order(StringComparer.Ordinal).ToList();

        throw new InvalidOperationException(
            mode == OperatingMode.Live
                ? "LIVE execution has no broker and will not be given one here: the live-trading gates are " +
                  "not implemented. Run the bot in PAPER or SANDBOX."
                : $"No broker supports {mode} on {venue}. Registered brokers: {string.Join(", ", registered)}.");
    }
}
