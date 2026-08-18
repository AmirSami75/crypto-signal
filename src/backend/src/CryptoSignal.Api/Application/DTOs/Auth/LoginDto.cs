using CryptoSignal.Auth.Application.DTOs.Auth;

namespace CryptoSignal.Api.Application.DTOs.Auth;

/// <summary>
/// Login credentials.
/// </summary>
public record LoginDto(string UserName, string Password) : BaseLoginDto(UserName, Password);
