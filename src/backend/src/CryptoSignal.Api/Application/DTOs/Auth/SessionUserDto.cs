using CryptoSignal.Auth.Application.DTOs.Auth;

namespace CryptoSignal.Api.Application.DTOs.Auth;

/// <summary>
/// Authenticated session: the token plus the roles and permissions the dashboard needs to
/// render its navigation.
/// </summary>
public class SessionUserDto : BaseSessionUserDto
{
    /// <summary>Functional role on the platform, resolved from <c>User.UserType</c>.</summary>
    public string? UserType { get; set; }
}
