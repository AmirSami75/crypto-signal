using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Auth;

/// <summary>
/// Functional role of a user on the trading platform. This is a descriptive attribute surfaced in
/// the JWT as <c>user_type</c>; it does not grant access on its own — authorization is driven
/// entirely by roles and permissions.
/// </summary>
public enum UserType
{
    /// <summary>Full platform administration.</summary>
    [Display(Name = "Administrator")] Administrator = 1,

    /// <summary>May authorize and manage live orders.</summary>
    [Display(Name = "Trader")] Trader = 2,

    /// <summary>Works with models, backtests and signals, but cannot authorize orders.</summary>
    [Display(Name = "Analyst")] Analyst = 3,

    /// <summary>Read-only access to signals and reports.</summary>
    [Display(Name = "Viewer")] Viewer = 4,
}
