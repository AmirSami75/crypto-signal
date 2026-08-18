using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Auth.Adapter.Repos.Contracts;

public interface ILoginHistoryRepo : IRepo<LoginHistory>
{
}