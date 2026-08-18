using CryptoSignal.Api.Application.DTOs.Auth;
using CryptoSignal.Auth.Application.Validators.Auth;

namespace CryptoSignal.Api.Application.Validators.Auth;

/// <summary>
/// Login request validation. Rules come from the Auth module's base validator; this concrete type
/// exists so FluentValidation's assembly scan can resolve <see cref="LoginDto"/>.
/// </summary>
public sealed class UserLoginValidator : BaseUserLoginValidator<LoginDto>;
