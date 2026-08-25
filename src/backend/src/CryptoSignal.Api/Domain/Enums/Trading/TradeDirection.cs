using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// Which way a bet points. The persisted counterpart of the ML contract's <c>MlDirection</c>; the
/// numeric values are deliberately identical so the wire value and the stored value cannot drift.
/// </summary>
public enum TradeDirection
{
    [Display(Name = "Long")] Long = 1,
    [Display(Name = "Short")] Short = 2,

    /// <summary>No position, and no reason to open one. A decision, not an absence of one.</summary>
    [Display(Name = "Flat")] Flat = 3,
}
