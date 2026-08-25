using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// The venue's own view of an order, normalised across adapters. Exchange state is authoritative for
/// orders and fills; this column records what the venue last said, not what the platform hoped.
/// </summary>
public enum ExchangeOrderStatus
{
    [Display(Name = "New")] New = 1,
    [Display(Name = "Partially filled")] PartiallyFilled = 2,
    [Display(Name = "Filled")] Filled = 3,
    [Display(Name = "Cancelled")] Cancelled = 4,
    [Display(Name = "Rejected")] Rejected = 5,
    [Display(Name = "Expired")] Expired = 6,

    /// <summary>
    /// The venue reported a state this platform does not model. Treated as an incident rather than
    /// coerced into a neighbouring value — an impossible order state is a kill-switch trigger.
    /// </summary>
    [Display(Name = "Unknown")] Unknown = 7,
}
