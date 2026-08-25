using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>How long a resting order stays workable. Explicit on every limit order, never defaulted.</summary>
public enum TimeInForce
{
    [Display(Name = "Good till cancel")] GoodTillCancel = 1,
    [Display(Name = "Immediate or cancel")] ImmediateOrCancel = 2,
    [Display(Name = "Fill or kill")] FillOrKill = 3,
}
