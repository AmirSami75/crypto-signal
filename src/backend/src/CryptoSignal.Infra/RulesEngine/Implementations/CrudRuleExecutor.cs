using CryptoSignal.Infra.RulesEngine.Contracts;

namespace CryptoSignal.Infra.RulesEngine.Implementations;

public sealed class CrudRuleExecutor<TInputDto, TEntity, TKey>(
    IRuleEngine<CreateCrudContext<TInputDto, TEntity>> createEngine,
    IRuleEngine<UpdateCrudContext<TInputDto, TEntity, TKey>> updateEngine,
    IRuleEngine<DeleteCrudContext<TEntity, TKey>> deleteEngine)
    : ICrudRuleExecutor<TInputDto, TEntity, TKey>
    where TInputDto : class
    where TEntity : class
    where TKey : struct
{
    public Task ValidateCreateAsync(
        TInputDto dto,
        TEntity entity,
        CancellationToken cancellationToken)
    {
        var context = new CreateCrudContext<TInputDto, TEntity>(
            dto,
            entity);

        return createEngine.ValidateAsync(
            context,
            cancellationToken);
    }

    public Task ValidateUpdateAsync(
        TKey id,
        TInputDto dto,
        TEntity currentEntity,
        CancellationToken cancellationToken)
    {
        var context =
            new UpdateCrudContext<TInputDto, TEntity, TKey>(
                id,
                dto,
                currentEntity);

        return updateEngine.ValidateAsync(
            context,
            cancellationToken);
    }

    public Task ValidateDeleteAsync(
        TKey id,
        TEntity entity,
        CancellationToken cancellationToken)
    {
        var context = new DeleteCrudContext<TEntity, TKey>(
            id,
            entity);

        return deleteEngine.ValidateAsync(
            context,
            cancellationToken);
    }
}