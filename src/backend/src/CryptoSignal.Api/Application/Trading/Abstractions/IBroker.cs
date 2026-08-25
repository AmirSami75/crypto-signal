using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Abstractions;

/// <summary>A venue that can be asked to place an order.</summary>
/// <remarks>
/// The only method that can move money in this codebase. It is reached from the bot scheduler and from
/// nowhere else — never from an HTTP request path (<c>docs/LIVE_TRADING_SAFETY.md</c>), and never before
/// <see cref="IRiskEngine"/> has allowed the intent it is placing.
/// </remarks>
public interface IBroker
{
    /// <summary>Short stable name for logs, audit summaries and error messages.</summary>
    string Name { get; }

    /// <summary>
    /// Whether this broker acts for a given mode and venue. A broker asked to act outside what it claims
    /// must throw.
    /// </summary>
    /// <remarks>
    /// The pair matters, not the venue alone. A simulator is correct for PAPER on every venue because it
    /// touches none of them; a real venue adapter is correct for exactly one venue and must never be
    /// reachable in PAPER, where the whole point is that no order leaves the process.
    /// </remarks>
    bool Supports(OperatingMode mode, MarketVenue venue);

    /// <summary>
    /// Submits the order. Must be idempotent on <c>ClientOrderId</c>: a retry of a request the venue
    /// already accepted reports that same order rather than placing a second one.
    /// </summary>
    Task<BrokerPlacement> PlaceAsync(BrokerOrderRequest request, CancellationToken cancellationToken);

    /// <summary>
    /// Re-reads an order the venue may or may not hold, by the client id it was submitted under. This
    /// is how an ambiguous write is resolved — see <see cref="BrokerOutcome.Ambiguous"/>.
    /// </summary>
    Task<BrokerPlacement> ReconcileAsync(
        string symbol,
        string clientOrderId,
        CancellationToken cancellationToken);

    /// <summary>
    /// Free balance of <paramref name="quoteAsset"/>, already net of what open orders reserve, or null
    /// when the venue could not be asked.
    /// </summary>
    /// <remarks>
    /// Null means "unknown", and the risk engine denies on it — an unknown balance is not a sufficient
    /// one. Returning zero instead would be a claim the account is empty, which reads as a different
    /// denial and, worse, would look like a successful read.
    /// </remarks>
    Task<decimal?> GetAvailableBalanceAsync(
        string quoteAsset,
        CancellationToken cancellationToken);
}

/// <summary>Picks the broker for a mode and venue. A miss is an error, never a silent default.</summary>
public interface IBrokerResolver
{
    IBroker Resolve(OperatingMode mode, MarketVenue venue);
}
