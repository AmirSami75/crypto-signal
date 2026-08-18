using CryptoSignal.Api.Domain.Enums.Auth;
using CryptoSignal.Auth.Domain.Models;

namespace CryptoSignal.Api.Domain.Models.Auth;

/// <summary>
/// Platform user. Concrete implementation of the Auth module's <see cref="BaseUser"/>.
/// </summary>
/// <remarks>
/// Crypto Signal has no branch hierarchy, so <see cref="BaseUser.BranchName"/> and
/// <see cref="BaseUser.BranchCode"/> are left at their <c>null</c> defaults; the JWT simply
/// omits those claims.
/// </remarks>
public class User : BaseUser
{
    #region Properties

    /// <summary>Mobile number, used for out-of-band notifications.</summary>
    public string? Mobile { get; set; }

    /// <summary>Functional role on the platform. Descriptive only — see <see cref="UserType"/>.</summary>
    public UserType? UserType { get; set; }

    #endregion
}
