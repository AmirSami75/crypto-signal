namespace CryptoSignal.Api.Domain.Constants;

/// <summary>
/// Names of the rate-limiting policies registered in <c>Program.cs</c>. Kept as constants so the
/// <c>[EnableRateLimiting]</c> attribute on an action and the policy registration cannot drift
/// apart — a mistyped policy name throws only when the endpoint is first hit.
/// </summary>
public static class RateLimitPolicies
{
    /// <summary>
    /// Guards the anonymous <c>POST /api/v1/auth/register</c> endpoint. Login needs no equivalent:
    /// it is already bounded by account lockout after
    /// <see cref="Auth.Domain.Constants.AuthGlobalVariables.NumberOfWrongPasswordsAllowed"/>
    /// failures, whereas nothing else limits how many accounts an anonymous caller can create.
    /// </summary>
    public const string Registration = "registration";

    /// <summary>Requests permitted per <see cref="RegistrationWindowMinutes"/> per client IP.</summary>
    public const int RegistrationPermitLimit = 5;

    /// <summary>Length of the fixed window applied to <see cref="Registration"/>, in minutes.</summary>
    public const int RegistrationWindowMinutes = 15;

    /// <summary>
    /// Guards the bot lifecycle endpoints — start, pause, stop — and per-bot kill-switch changes.
    /// These do not place orders themselves; they decide whether the scheduler may. Bounding them is
    /// about the audit trail rather than about load: a start/stop loop hammered by a stuck client
    /// writes a status history nobody can read, and an operator looking for the moment a bot was
    /// halted should not have to page through hundreds of identical rows to find it.
    /// </summary>
    public const string BotControl = "bot-control";

    /// <summary>Requests permitted per <see cref="BotControlWindowMinutes"/> per caller.</summary>
    public const int BotControlPermitLimit = 30;

    /// <summary>Length of the fixed window applied to <see cref="BotControl"/>, in minutes.</summary>
    public const int BotControlWindowMinutes = 1;

    /// <summary>
    /// Guards the platform-wide kill switch. Deliberately looser than <see cref="BotControl"/> in one
    /// direction that matters: engaging a switch is the safe action, and an operator stopping trading
    /// in an emergency must never be told to wait. The limit exists so a scripted caller cannot churn
    /// the switch on and off, not to slow a person down.
    /// </summary>
    public const string KillSwitchControl = "kill-switch-control";

    /// <summary>Requests permitted per <see cref="KillSwitchWindowMinutes"/> per caller.</summary>
    public const int KillSwitchPermitLimit = 60;

    /// <summary>Length of the fixed window applied to <see cref="KillSwitchControl"/>, in minutes.</summary>
    public const int KillSwitchWindowMinutes = 1;
}
