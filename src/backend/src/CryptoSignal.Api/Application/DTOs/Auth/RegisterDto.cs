using System.ComponentModel.DataAnnotations;
using CryptoSignal.Infra.Extensions.Type;

namespace CryptoSignal.Api.Application.DTOs.Auth;

/// <summary>
/// Self-registration payload for the anonymous <c>POST /api/v1/auth/register</c> endpoint.
/// </summary>
/// <remarks>
/// <para>
/// The omissions here are the security control, not an oversight. This type deliberately exposes
/// none of <c>Roles</c>, <c>UserType</c>, <c>ParentId</c>, <c>Id</c>, <c>IsActive</c> or
/// <c>PersonelCode</c>, so an anonymous caller has no way to grant itself a role, claim a
/// privileged user type, graft itself onto another account's hierarchy, or activate its own
/// account. Reusing <see cref="UserInputDto"/> for registration would hand out exactly those
/// levers — its <c>Roles</c> list is not only bindable but <em>required</em>, which is why the
/// authenticated create endpoint cannot serve this purpose.
/// </para>
/// <para>
/// Any unrecognised properties in the request body are ignored by the model binder, so posting
/// <c>"roles"</c> or <c>"userType"</c> alongside these fields has no effect.
/// </para>
/// </remarks>
public record RegisterDto(
    string FullName,
    string UserName,
    string Password,
    string ConfirmPassword,
    string? Email,
    string? Mobile) : IValidatableObject
{
    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (string.IsNullOrWhiteSpace(UserName))
            yield return new ValidationResult("نام کاربری اجباری است", [nameof(UserName)]);

        if (string.IsNullOrWhiteSpace(FullName))
            yield return new ValidationResult("نام و نام خانوادگی اجباری است", [nameof(FullName)]);

        if (string.IsNullOrWhiteSpace(Password))
            yield return new ValidationResult("وارد نمودن کلمه عبور اجباری است", [nameof(Password)]);

        if (string.IsNullOrWhiteSpace(ConfirmPassword))
            yield return new ValidationResult("وارد نمودن تکرار کلمه عبور اجباری است", [nameof(ConfirmPassword)]);

        // Same wording as BaseChangePasswordDto so a user meets one rule set, described one way,
        // wherever they set a password.
        if (!string.IsNullOrWhiteSpace(Password) && !Password.IsStrongPassword())
            yield return new ValidationResult(
                "کلمه عبور باید حداقل 8 کارکتر شامل یک کارکتر کوچک انگلیسی، یک کارکتر بزرگ انگلیسی، یک کارکتر خاص و عدد باشد",
                [nameof(Password)]);

        if (Password != ConfirmPassword)
            yield return new ValidationResult("کلمه عبور و تکرار آن با یکدیگر مغایرت دارد", [nameof(ConfirmPassword)]);

        if (!string.IsNullOrEmpty(Email) && !Email.IsValidEmail())
            yield return new ValidationResult("ایمیل نامعتبر است", [nameof(Email)]);

        // IsValidPhone rather than IsValidMobile, matching UserInputDto: its pattern accepts a
        // leading-zero Iranian mobile (09xxxxxxxxx) as well as a landline.
        if (!string.IsNullOrEmpty(Mobile) && !Mobile.IsValidPhone())
            yield return new ValidationResult("شماره همراه نامعتبر است", [nameof(Mobile)]);
    }
}
