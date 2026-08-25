using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>Lifecycle of a bot. Only <see cref="Active"/> is scheduled for evaluation.</summary>
public enum BotStatus
{
    /// <summary>Configured but never started. The scheduler ignores it.</summary>
    [Display(Name = "Draft")] Draft = 1,

    /// <summary>Scheduled. Evaluated on its cadence.</summary>
    [Display(Name = "Active")] Active = 2,

    /// <summary>Temporarily halted by an operator. Positions stay open; no new intents.</summary>
    [Display(Name = "Paused")] Paused = 3,

    /// <summary>Halted deliberately and durably.</summary>
    [Display(Name = "Stopped")] Stopped = 4,

    /// <summary>
    /// Halted by the platform after an error it must not trade through — a missing candle window, an
    /// ambiguous order outcome, a reconciliation mismatch. Requires an operator to clear.
    /// </summary>
    [Display(Name = "Faulted")] Faulted = 5,
}
