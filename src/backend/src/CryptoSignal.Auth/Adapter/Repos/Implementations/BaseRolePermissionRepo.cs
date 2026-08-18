using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB.AbstractRepo;

namespace CryptoSignal.Auth.Adapter.Repos.Implementations;

public abstract class BaseRolePermissionRepo<TContext>(TContext dbCtx) : Repo<RolePermission>(dbCtx), IRolePermissionRepo
    where TContext : DbContext
{
}