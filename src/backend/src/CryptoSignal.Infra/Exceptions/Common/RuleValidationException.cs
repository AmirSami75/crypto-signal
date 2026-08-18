using CryptoSignal.Infra.RulesEngine.Contracts;

namespace CryptoSignal.Infra.Exceptions.Common;

public sealed class RuleValidationException(IReadOnlyList<RuleFailure> failures)
    : Exception("One or more business rules failed.")
{
    public IReadOnlyList<RuleFailure> Failures { get; } = failures;
}