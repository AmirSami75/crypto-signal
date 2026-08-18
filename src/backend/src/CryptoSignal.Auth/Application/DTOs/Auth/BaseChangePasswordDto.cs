using CryptoSignal.Infra.Extensions.Type;
using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Auth.Application.DTOs.Auth;

public abstract record BaseChangePasswordDto(string CurrentPass, string NewPass, string ConfirmNewPass) : IValidatableObject
{
    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (string.IsNullOrWhiteSpace(CurrentPass))
            yield return new ValidationResult("وارد نمودن کلمه عبور اجباری است", new[] { nameof(CurrentPass) });

        if (string.IsNullOrWhiteSpace(NewPass))
            yield return new ValidationResult("وارد نمودن کلمه عبور جدید اجباری است", new[] { nameof(NewPass) });

        if (string.IsNullOrWhiteSpace(ConfirmNewPass))
            yield return new ValidationResult("وارد نمودن تکرار کلمه جدید عبور اجباری است", new[] { nameof(ConfirmNewPass) });

        if (!CurrentPass.IsStrongPassword())
            yield return new ValidationResult("کلمه عبور باید حداقل 8 کارکتر شامل یک کارکتر کوچک انگلیسی، یک کارکتر بزرگ انگلیسی، یک کارکتر خاص و عدد باشد", new[] { nameof(CurrentPass) });

        if (!NewPass.IsStrongPassword())
            yield return new ValidationResult("کلمه عبور جدید باید حداقل 8 کارکتر شامل یک کارکتر کوچک انگلیسی، یک کارکتر بزرگ انگلیسی، یک کارکتر خاص و عدد باشد", new[] { nameof(NewPass) });

        if (!ConfirmNewPass.IsStrongPassword())
            yield return new ValidationResult("تکرار کلمه عبور جدید باید حداقل 8 کارکتر شامل یک کارکتر کوچک انگلیسی، یک کارکتر بزرگ انگلیسی، یک کارکتر خاص و عدد باشد", new[] { nameof(ConfirmNewPass) });

        if (NewPass != ConfirmNewPass)
            yield return new ValidationResult("کلمه عبور جدید و تکرار آن با یکدیگر مغایرت دارد", new[] { nameof(ConfirmNewPass) });

    }
}
