namespace CryptoSignal.Infra.RulesEngine.Contracts;

// a single failure (code + message + optional payload)
public sealed record RuleFailure(string Code, string Message, object? Data = null);

// result of running one rule
public sealed record RuleResult
{
    public bool IsSuccess { get; }
    public IReadOnlyList<RuleFailure> Failures { get; }

    private RuleResult(
        bool isSuccess,
        IReadOnlyList<RuleFailure> failures)
    {
        IsSuccess = isSuccess;
        Failures = failures;
    }

    public static RuleResult Success() =>
        new(true, []);

    public static RuleResult Fail(
        string code,
        string message,
        object? data = null) =>
        new(false, [new RuleFailure(code, message, data)]);

    public static RuleResult Fail(params RuleFailure[] failures)
    {
        ArgumentNullException.ThrowIfNull(failures);

        if (failures.Length == 0)
        {
            throw new ArgumentException(
                "At least one rule failure must be provided.",
                nameof(failures));
        }

        return new RuleResult(false, failures);
    }
}