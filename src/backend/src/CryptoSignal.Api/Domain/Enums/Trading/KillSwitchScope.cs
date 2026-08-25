using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// How wide a kill switch reaches. The scopes are independent and checked together — a bot is blocked
/// if any switch covering it is engaged, so a narrow switch can never unblock what a wider one stopped.
/// </summary>
public enum KillSwitchScope
{
    /// <summary>Everything, every mode, every venue.</summary>
    [Display(Name = "Global")] Global = 1,

    /// <summary>One operating mode. Sandbox can be stopped without touching paper.</summary>
    [Display(Name = "Operating mode")] OperatingMode = 2,

    /// <summary>One venue.</summary>
    [Display(Name = "Exchange")] Exchange = 3,

    /// <summary>One bot.</summary>
    [Display(Name = "Bot")] Bot = 4,

    /// <summary>One instrument, across every bot that trades it.</summary>
    [Display(Name = "Symbol")] Symbol = 5,
}
