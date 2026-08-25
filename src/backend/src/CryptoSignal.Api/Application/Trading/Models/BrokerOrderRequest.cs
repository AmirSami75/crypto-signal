using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Models;

/// <summary>The order to place, flattened from an allowed <c>OrderIntent</c>.</summary>
/// <remarks>
/// <para>
/// <c>ClientOrderId</c> is the idempotency key and is computed deterministically from the strategy
/// decision, so a retry after a dropped response carries the same id the venue may already hold. It is
/// the only reason an ambiguous submission is recoverable rather than a coin flip.
/// </para>
/// <para>
/// <c>Rules</c> travels with the order because a broker has to quantize to the venue's grid, and the
/// grid the order was sized and risk-checked against is the one it must be filled on. Re-fetching it
/// here would let a filter that changed mid-tick be applied to an order approved under the old one.
/// </para>
/// </remarks>
public sealed record BrokerOrderRequest(
    string ClientOrderId,
    string Symbol,
    MarketVenue Venue,
    InstrumentRules Rules,
    TradeDirection Direction,
    OrderSide Side,
    OrderType Type,
    decimal Quantity,
    decimal ReferencePrice,
    decimal? LimitPrice = null,
    decimal? TakeProfitPrice = null,
    decimal? StopLossPrice = null,
    TimeInForce? TimeInForce = null,
    int MaxSlippageBps = 0);

/// <summary>How a submission ended.</summary>
public enum BrokerOutcome
{
    /// <summary>The venue accepted the order and said so.</summary>
    Accepted = 1,

    /// <summary>The venue refused it, and the refusal is trustworthy — nothing is working.</summary>
    Rejected = 2,

    /// <summary>
    /// The request left but no usable answer came back. The order may or may not exist at the venue.
    /// </summary>
    /// <remarks>
    /// This is the state that must never be guessed at. The caller reconciles by client order id and,
    /// until it resolves, places nothing further for the bot — an assumed-failed order that actually
    /// filled leaves an untracked position, which is worse than being stopped.
    /// </remarks>
    Ambiguous = 3,
}

/// <summary>What the venue reported, plus hashes of the traffic that produced it.</summary>
/// <remarks>
/// <c>RequestHash</c> and <c>ResponseHash</c> are SHA-256 digests, never the payloads: a signed exchange
/// request carries an HMAC of the secret key and must not be persisted or logged verbatim.
/// </remarks>
public sealed record BrokerPlacement(
    BrokerOutcome Outcome,
    ExchangeOrderStatus Status,
    string? VenueOrderId,
    decimal FilledQuantity,
    decimal? AverageFillPrice,
    IReadOnlyList<BrokerFill> Fills,
    string? RequestHash = null,
    string? ResponseHash = null,
    string? Detail = null,
    DateTimeOffset? VenueUpdatedAt = null);

/// <summary>One execution the venue reported.</summary>
public sealed record BrokerFill(
    string VenueTradeId,
    decimal Price,
    decimal Quantity,
    decimal Fee,
    string FeeAsset,
    DateTimeOffset ExecutedAt,
    bool? IsMaker = null);
