using System.ComponentModel.DataAnnotations;
using CryptoSignal.Api.Domain.Enums.Auth;
using CryptoSignal.Auth.Application.DTOs.Users;
using CryptoSignal.Infra.Extensions.Type;

namespace CryptoSignal.Api.Application.DTOs.Auth;

/// <summary>
/// Payload for creating or updating a user.
/// </summary>
public record UserInputDto : BaseUserInputDto
{
    public string? Mobile { get; init; }

    public UserType? UserType { get; init; }

    public override IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        // The base rules are not automatically part of this iterator: yield them through explicitly.
        foreach (var result in base.Validate(validationContext))
            yield return result;

        if (!string.IsNullOrEmpty(Mobile) && !Mobile.IsValidPhone())
            yield return new ValidationResult("شماره همراه نامعتبر است", [nameof(Mobile)]);

        if (UserType is not null && !Enum.IsDefined(UserType.Value))
            yield return new ValidationResult("نوع کاربری نامعتبر است", [nameof(UserType)]);
    }
}
