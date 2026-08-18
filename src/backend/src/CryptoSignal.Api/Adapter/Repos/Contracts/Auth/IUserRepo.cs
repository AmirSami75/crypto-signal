using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Adapter.Repos.Contracts;

namespace CryptoSignal.Api.Adapter.Repos.Contracts.Auth;

/// <summary>
/// Repository over the concrete <see cref="User"/> entity.
/// </summary>
public interface IUserRepo : IBaseUserRepo<User>;
