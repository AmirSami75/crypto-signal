namespace CryptoSignal.Infra.RulesEngine.Contracts;

public interface IRule<in TContext>
{
    Task<RuleResult> CheckAsync(TContext ctx, CancellationToken ct);
}