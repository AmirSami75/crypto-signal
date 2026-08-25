using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// The venue's order, as this platform last understood it. One row per <see cref="OrderIntent"/> that
/// actually reached a venue; the venue's state is authoritative and this row is the platform's durable
/// mirror of it.
/// </summary>
/// <remarks>
/// <para>
/// The request and response payloads are stored as SHA-256 hashes, never as bodies. The bodies carry
/// signed parameters and headers that the safety policy forbids persisting, and a hash is enough to
/// prove that what was sent matches what a replay reconstructs without keeping the sensitive material
/// around to leak.
/// </para>
/// <para>
/// <see cref="VenueOrderId"/> is null in exactly one situation that matters: a submission whose outcome
/// was ambiguous. That is not an error to be overwritten — it is the state reconciliation resolves by
/// looking the order up by <see cref="OrderIntent.ClientOrderId"/>, and until it is resolved the bot
/// places nothing new.
/// </para>
/// </remarks>
public class ExchangeOrder : BaseEntity
{
    /// <summary>The intent this order came from.</summary>
    public Guid OrderIntentId { get; set; }

    /// <summary>The bot, copied for direct querying.</summary>
    public Guid BotId { get; set; }

    /// <summary>Which venue class this order belongs to. Filtered on every read.</summary>
    public OperatingMode OperatingMode { get; set; }

    /// <summary>Which venue holds it.</summary>
    public MarketVenue Venue { get; set; }

    /// <summary>The venue's own order id, or null while a submission's outcome is unresolved.</summary>
    public string? VenueOrderId { get; set; }

    /// <summary>The client order id echoed back, for reconciliation.</summary>
    public string ClientOrderId { get; set; } = string.Empty;

    /// <summary>The venue's status, normalised across adapters.</summary>
    public ExchangeOrderStatus Status { get; set; }

    /// <summary>Base-asset quantity filled so far.</summary>
    public decimal FilledQuantity { get; set; }

    /// <summary>Quantity-weighted average fill price so far, when there is a fill.</summary>
    public decimal? AverageFillPrice { get; set; }

    /// <summary>SHA-256 of the submitted request payload. Never the payload itself.</summary>
    public string? RequestHash { get; set; }

    /// <summary>SHA-256 of the venue's response payload.</summary>
    public string? ResponseHash { get; set; }

    /// <summary>When the order was submitted.</summary>
    public DateTime SubmittedAt { get; set; }

    /// <summary>Venue-reported time of the last state change, when supplied.</summary>
    public DateTime? VenueUpdatedAt { get; set; }

    /// <summary>When the platform last reconciled this order against the venue.</summary>
    public DateTime? LastReconciledAt { get; set; }
}
