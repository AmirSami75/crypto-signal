namespace CryptoSignal.Infra.RulesEngine;

public interface ICrudRuleExecutor<in TInputDto, in TEntity, in TKey>
    where TInputDto : class
    where TEntity : class
    where TKey : struct
{
    Task ValidateCreateAsync(
        TInputDto dto,
        TEntity entity,
        CancellationToken cancellationToken);

    Task ValidateUpdateAsync(
        TKey id,
        TInputDto dto,
        TEntity currentEntity,
        CancellationToken cancellationToken);

    Task ValidateDeleteAsync(
        TKey id,
        TEntity entity,
        CancellationToken cancellationToken);
}