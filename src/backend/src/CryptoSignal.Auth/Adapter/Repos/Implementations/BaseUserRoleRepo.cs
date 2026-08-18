using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB.AbstractRepo;

namespace CryptoSignal.Auth.Adapter.Repos.Implementations;

public abstract class BaseUserRoleRepo<TContext>(TContext dbCtx) : Repo<UserRole>(dbCtx), IUserRoleRepo
    where TContext : DbContext
{
}