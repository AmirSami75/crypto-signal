using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Auth.Adapter.Repos.Contracts;

public interface IBaseUserRepo<T> : IRepo<T> where T : BaseEntity
{
}