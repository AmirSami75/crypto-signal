namespace CryptoSignal.Infra.RulesEngine.Contracts;

public sealed record CreateCrudContext<TInputDto, TEntity>(
    TInputDto Dto,
    TEntity Entity)
    where TInputDto : class
    where TEntity : class;

public sealed record UpdateCrudContext<TInputDto, TEntity, TKey>(
    TKey Id,
    TInputDto Dto,
    TEntity CurrentEntity)
    where TInputDto : class
    where TEntity : class
    where TKey : struct;

public sealed record DeleteCrudContext<TEntity, TKey>(
    TKey Id,
    TEntity Entity)
    where TEntity : class
    where TKey : struct;