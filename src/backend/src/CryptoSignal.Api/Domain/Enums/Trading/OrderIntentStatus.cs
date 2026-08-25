using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// How far an intent got. An intent is immutable in its trading parameters; this column is the one
/// thing about it that moves, and it only ever moves forward.
/// </summary>
/// <remarks>
/// <see cref="Ambiguous"/> is the state the safety policy cares most about: the submission may or may
/// not have reached the venue. It is not a failure and must never be retried blindly — it is resolved
/// by reconciling on the client order id, and while it is unresolved the bot places nothing further.
/// </remarks>
public enum OrderIntentStatus
{
    /// <summary>Constructed, not yet risk-checked.</summary>
    [Display(Name = "Draft")] Draft = 1,

    /// <summary>Denied by the risk engine. Terminal.</summary>
    [Display(Name = "Risk denied")] RiskDenied = 2,

    /// <summary>Passed risk, awaiting the human approval a restricted-live order requires.</summary>
    [Display(Name = "Awaiting approval")] AwaitingApproval = 3,

    /// <summary>Cleared to submit.</summary>
    [Display(Name = "Approved")] Approved = 4,

    /// <summary>Handed to the venue; no acknowledgement yet.</summary>
    [Display(Name = "Submitted")] Submitted = 5,

    /// <summary>Acknowledged and partly filled.</summary>
    [Display(Name = "Partially filled")] PartiallyFilled = 6,

    /// <summary>Completely filled. Terminal.</summary>
    [Display(Name = "Filled")] Filled = 7,

    /// <summary>Cancelled before completing. Terminal.</summary>
    [Display(Name = "Cancelled")] Cancelled = 8,

    /// <summary>Refused by the venue. Terminal.</summary>
    [Display(Name = "Rejected")] Rejected = 9,

    /// <summary>Failed before reaching the venue, provably. Terminal.</summary>
    [Display(Name = "Failed")] Failed = 10,

    /// <summary>Outcome unknown. Blocks further orders until reconciled.</summary>
    [Display(Name = "Ambiguous")] Ambiguous = 11,
}
