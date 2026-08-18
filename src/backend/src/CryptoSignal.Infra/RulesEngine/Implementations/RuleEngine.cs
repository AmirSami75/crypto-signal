using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.RulesEngine.Contracts;

namespace CryptoSignal.Infra.RulesEngine.Implementations;

internal sealed class RuleEngine<TContext>(
    IEnumerable<IRule<TContext>> rules)
    : IRuleEngine<TContext>
{
    private readonly IReadOnlyList<IRule<TContext>> _rules =
        rules.ToArray();

    public async Task ValidateAsync(
        TContext context,
        CancellationToken cancellationToken = default)
    {
        foreach (var rule in _rules)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var result = await rule.CheckAsync(
                context,
                cancellationToken);

            if (!result.IsSuccess)
            {
                throw new LogicException(
                    result.Failures
                        .Select(s => string.Join(',', s.Message))
                        .ToString(),
                    result.Failures);
            }
        }
    }
}