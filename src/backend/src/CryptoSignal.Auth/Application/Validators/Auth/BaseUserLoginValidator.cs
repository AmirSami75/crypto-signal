using FluentValidation;
using CryptoSignal.Auth.Application.DTOs.Auth;

namespace CryptoSignal.Auth.Application.Validators.Auth;

public abstract class BaseUserLoginValidator<TInVal> : AbstractValidator<TInVal>
    where TInVal : BaseLoginDto
{
    protected BaseUserLoginValidator()
    {
        ClassLevelCascadeMode = CascadeMode.Stop;
        RuleLevelCascadeMode = CascadeMode.Stop;

        RuleFor(x => x.UserName)
            .NotEmpty().WithMessage("نام کاربری اجباری است.")
            .MinimumLength(3).WithMessage("نام کاربری نمیتواند کمتر از  3 کاراکتر باشد.")
            .MaximumLength(20).WithMessage("نام کاربری نمیتواند بیشتر از 20 کاراکتر باشد.");

        RuleFor(x => x.Password)
            .NotEmpty().WithMessage("رمز عبور اجباری است.");
    }
}