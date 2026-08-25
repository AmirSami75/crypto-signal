using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// Why a position ended. The first five mirror the engine's reason-code vocabulary; the last three are
/// the orchestrator's own, because the engine cannot know about them.
/// </summary>
public enum PositionCloseReason
{
    [Display(Name = "Take profit touched")] TakeProfitTouched = 1,
    [Display(Name = "Stop loss touched")] StopLossTouched = 2,
    [Display(Name = "Max holding periods reached")] MaxHoldingPeriodsReached = 3,
    [Display(Name = "Direction reversed")] DirectionReversed = 4,

    /// <summary>Closed by an operator.</summary>
    [Display(Name = "Manual")] Manual = 5,

    /// <summary>Closed because a kill switch in scope was engaged.</summary>
    [Display(Name = "Kill switch")] KillSwitch = 6,

    /// <summary>Closed because the bot faulted.</summary>
    [Display(Name = "Bot faulted")] BotFaulted = 7,
}
