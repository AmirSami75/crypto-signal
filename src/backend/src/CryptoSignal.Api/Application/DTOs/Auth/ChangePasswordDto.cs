using CryptoSignal.Auth.Application.DTOs.Auth;

namespace CryptoSignal.Api.Application.DTOs.Auth;

/// <summary>
/// Password change request. Strength rules are enforced by the base type.
/// </summary>
public record ChangePasswordDto(string CurrentPass, string NewPass, string ConfirmNewPass)
    : BaseChangePasswordDto(CurrentPass, NewPass, ConfirmNewPass);
