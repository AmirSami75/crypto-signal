using System.Text.RegularExpressions;
using FluentValidation;
using MassTransit.Serialization;

namespace CryptoSignal.Infra.Extensions.Validator;

public static class RuleBuilderExtensions
{
    private static readonly Regex PersianDateRegex =
        new(@"^\d{4}/\d{1,2}/\d{1,2}$", RegexOptions.Compiled);

    /// <summary>
    /// Ensures Guid is not Guid.Empty.
    /// </summary>
    public static IRuleBuilderOptions<T, Guid> NotEmptyGuid<T>(this IRuleBuilder<T, Guid> ruleBuilder) =>
        ruleBuilder.Must(g => g != Guid.Empty)
            .WithMessage("شناسه نباید خالی باشد.");

    /// <summary>
    /// For optional strings: if provided, it must not be whitespace.
    /// </summary>
    public static IRuleBuilderOptions<T, string?> OptionalNotWhiteSpace<T>(
        this IRuleBuilder<T, string?> ruleBuilder) =>
        ruleBuilder.Must(s => s is null || !string.IsNullOrWhiteSpace(s))
            .WithMessage("مقدار رشته نباید فقط فاصله باشد.");

    /// <summary>
    /// For optional numeric values: if provided, must be greater than value.
    /// </summary>
    public static IRuleBuilderOptions<T, decimal?> OptionalGreaterThan<T>(
        this IRuleBuilder<T, decimal?> ruleBuilder, decimal threshold) =>
        ruleBuilder.Must(v => !v.HasValue || v.Value > threshold)
            .WithMessage($"مقدار باید بزرگ‌تر از {threshold} باشد.");

    /// <summary>
    /// For optional numeric values: if provided, must be >= value.
    /// </summary>
    public static IRuleBuilderOptions<T, decimal?> OptionalGreaterOrEqual<T>(
        this IRuleBuilder<T, decimal?> ruleBuilder, decimal threshold) =>
        ruleBuilder.Must(v => !v.HasValue || v.Value >= threshold)
            .WithMessage($"مقدار باید بزرگ‌تر یا مساوی {threshold} باشد.");

    /// <summary>
    /// For optional double values: if provided, must be within inclusive range.
    /// </summary>
    public static IRuleBuilderOptions<T, double> BetweenInclusive<T>(
        this IRuleBuilder<T, double> ruleBuilder, double min, double max) =>
        ruleBuilder.InclusiveBetween(min, max)
            .WithMessage($"مقدار باید بین {min} و {max} باشد.");


    /// <summary>
    /// If the string is empty/whitespace, it’s allowed.
    /// Otherwise, it must match YYYY/M/D (e.g., 1403/6/1 or 2025/9/13).
    /// </summary>
    public static IRuleBuilderOptions<T, string?> OptionalFormattedPersianDate<T>(
        this IRuleBuilder<T, string?> ruleBuilder,
        string propertyName)
    {
        return ruleBuilder
            .Must((_, value) => string.IsNullOrWhiteSpace(value) || PersianDateRegex.IsMatch(value!))
            .WithMessage($"{propertyName} باید به صورت YYYY/M/D باشد.");
    }
}