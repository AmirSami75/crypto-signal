using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>Which side of the book an order sits on.</summary>
/// <remarks>
/// Distinct from <see cref="TradeDirection"/>: opening a long and closing a short are both
/// <see cref="Buy"/>, so the direction cannot be recovered from the side alone.
/// </remarks>
public enum OrderSide
{
    [Display(Name = "Buy")] Buy = 1,
    [Display(Name = "Sell")] Sell = 2,
}
