using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Infra.Base.API.DTO;
using CryptoSignal.Infra.Extensions.Type;
using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Auth.Application.DTOs.Users;

public abstract record BaseUserInputDto :
    IValidatableObject
{
    public Guid Id { get; set; }
    public string FullName { get; init; }
    public string UserName { get; init; }
    public string? Phone { get; init; }
    public string? PersonelCode { get; init; }
    public string? Address { get; init; }
    public string? Email { get; init; }
    public Guid? ParentId { get; set; }

    public List<RolesIdsDto> Roles { get; set; }

    public virtual IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (string.IsNullOrWhiteSpace(UserName))
            yield return new ValidationResult("نام کاربری اجباری است", new[] { nameof(UserName) });

        if (string.IsNullOrWhiteSpace(FullName))
            yield return new ValidationResult("نام و نام خانوادگی اجباری است", new[] { nameof(FullName) });

        if (!string.IsNullOrEmpty(Email))
            if (!Email.IsValidEmail())
                yield return new ValidationResult("ایمیل نامعتبر است", new[] { nameof(Email) });

        if (!string.IsNullOrEmpty(Phone))
            if (!Phone.IsValidPhone())
                yield return new ValidationResult("تلفن نامعتبر است", new[] { nameof(Phone) });

        if (!string.IsNullOrEmpty(PersonelCode))
            if (!PersonelCode.IsValidPersonalCode())
                yield return new ValidationResult("کد پرسنلی بایستی فقط شامل عدد باش", new[] { nameof(PersonelCode) });

        if (Roles.Count == 0)
            yield return new ValidationResult("نقشی به کاربر اختصاص داده نشده است", new[] { nameof(Roles) });
    }
}