using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB.AbstractRepo;

namespace CryptoSignal.Auth.Adapter.Repos.Implementations;

public abstract class BaseLoginHistoryRepo<TContext>(TContext dbCtx) : Repo<LoginHistory>(dbCtx), ILoginHistoryRepo
    where TContext : DbContext
{
}