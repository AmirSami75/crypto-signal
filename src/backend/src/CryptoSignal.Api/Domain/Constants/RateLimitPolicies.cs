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
}
