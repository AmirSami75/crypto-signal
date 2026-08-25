using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// One execution against an <see cref="ExchangeOrder"/> — a price, a quantity, and the fee the venue
/// actually charged. An order fills in one or many of these.
/// </summary>
/// <remarks>
/// The fee is recorded in whatever asset the venue charged it in, because a fee taken in the base asset
/// and one taken in a discount token are different quantities that cannot be added, and collapsing them
/// to a single currency at record time would bake in a conversion the audit could never unwind. The
/// unique <c>(venue, venueTradeId)</c> index makes a re-delivered fill event idempotent: the same
/// execution seen twice is stored once.
/// </remarks>
public class OrderFill : BaseEntity
{
    /// <summary>The exchange order this fill belongs to.</summary>
    public Guid ExchangeOrderId { get; set; }

    /// <summary>The bot, copied for direct querying.</summary>
    public Guid BotId { get; set; }

    /// <summary>Which venue class this fill belongs to. Filtered on every read.</summary>
    public OperatingMode OperatingMode { get; set; }

    /// <summary>Which venue reported it.</summary>
    public MarketVenue Venue { get; set; }

    /// <summary>The venue's trade id. Unique per venue — the idempotency key for fills.</summary>
    public string VenueTradeId { get; set; } = string.Empty;

    /// <summary>Execution price.</summary>
    public decimal Price { get; set; }

    /// <summary>Base-asset quantity executed.</summary>
    public decimal Quantity { get; set; }

    /// <summary>Fee charged.</summary>
    public decimal Fee { get; set; }

    /// <summary>Asset the fee was charged in.</summary>
    public string FeeAsset { get; set; } = string.Empty;

    /// <summary>True when this platform was the resting side (maker), when the venue distinguishes.</summary>
    public bool? IsMaker { get; set; }

    /// <summary>Venue-reported execution time.</summary>
    public DateTime ExecutedAt { get; set; }
}
