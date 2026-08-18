using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Auth.Adapter.Repos.Implementations;

public abstract class BaseUserRepo<TContext,TEntity>(TContext dbCtx) : Repo<TEntity>(dbCtx), IBaseUserRepo<TEntity>  
    where TContext : DbContext
    where TEntity : BaseEntity
{
}