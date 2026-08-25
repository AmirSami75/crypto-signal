using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// Order types the platform is allowed to construct. Deliberately a short list: the safety policy
/// restricts operation to explicitly approved spot types, so an unlisted type cannot be expressed.
/// </summary>
public enum OrderType
{
    /// <summary>Immediate fill at whatever the book offers. Requires a notional cap and a slippage guard.</summary>
    [Display(Name = "Market")] Market = 1,

    /// <summary>Fill at a stated price or better. Requires a price-distance guard and a time-in-force.</summary>
    [Display(Name = "Limit")] Limit = 2,

    /// <summary>Becomes a market order when the stop price trades. The protective half of a bracket.</summary>
    [Display(Name = "Stop loss")] StopLoss = 3,

    /// <summary>Becomes a limit order when the stop price trades.</summary>
    [Display(Name = "Stop loss limit")] StopLossLimit = 4,

    /// <summary>Becomes a market order when the target price trades. The profit half of a bracket.</summary>
    [Display(Name = "Take profit")] TakeProfit = 5,

    /// <summary>Becomes a limit order when the target price trades.</summary>
    [Display(Name = "Take profit limit")] TakeProfitLimit = 6,
}
