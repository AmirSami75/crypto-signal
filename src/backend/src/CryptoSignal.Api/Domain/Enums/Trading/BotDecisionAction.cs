using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// What the engine advised, and what the orchestrator therefore did. Mirrors the ML contract's
/// <c>MlBotAction</c> numerically.
/// </summary>
/// <remarks>
/// <see cref="Close"/> is advice that the position's bracket is through — the engine holds no state
/// and closes nothing itself. The orchestrator is what acts.
/// </remarks>
public enum BotDecisionAction
{
    [Display(Name = "Hold")] Hold = 1,
    [Display(Name = "Open")] Open = 2,
    [Display(Name = "Close")] Close = 3,

    /// <summary>Keep the position, move the bracket to the returned levels.</summary>
    [Display(Name = "Adjust bracket")] AdjustBracket = 4,
}
