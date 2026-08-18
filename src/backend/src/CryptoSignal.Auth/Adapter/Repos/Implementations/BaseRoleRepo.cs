using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB.AbstractRepo;

namespace CryptoSignal.Auth.Adapter.Repos.Implementations;

public abstract class BaseRoleRepo<TContext>(TContext dbCtx) : Repo<Role>(dbCtx), IRoleRepo
    where TContext : DbContext
{
}