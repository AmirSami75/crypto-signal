namespace CryptoSignal.Infra.RulesEngine.Contracts;

public interface IRuleEngine<TContext>
{
    Task ValidateAsync(TContext ctx, CancellationToken ct = default);
}