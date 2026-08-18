using CryptoSignal.Api.Adapter.Persistence.Contexts;
using CryptoSignal.Api.Adapter.Repos.Contracts.Auth;
using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Adapter.Repos.Implementations;

namespace CryptoSignal.Api.Adapter.Repos.Implementations.Auth;

/// <summary>
/// Concrete repositories closing the Auth module's open generic bases over
/// <see cref="CryptoSignalDbContext"/>. These thin wrappers exist so the Scrutor scan in
/// <c>Program.cs</c> has closed types to register against <c>IRepo&lt;&gt;</c>.
/// </summary>
public sealed class UserRepo(CryptoSignalDbContext ctx)
    : BaseUserRepo<CryptoSignalDbContext, User>(ctx), IUserRepo;

/// <inheritdoc cref="UserRepo"/>
public sealed class PermissionRepo(CryptoSignalDbContext ctx)
    : BasePermissionRepo<CryptoSignalDbContext>(ctx);

/// <inheritdoc cref="UserRepo"/>
public sealed class RoleRepo(CryptoSignalDbContext ctx)
    : BaseRoleRepo<CryptoSignalDbContext>(ctx);

/// <inheritdoc cref="UserRepo"/>
public sealed class RolePermissionRepo(CryptoSignalDbContext ctx)
    : BaseRolePermissionRepo<CryptoSignalDbContext>(ctx);

/// <inheritdoc cref="UserRepo"/>
public sealed class UserRoleRepo(CryptoSignalDbContext ctx)
    : BaseUserRoleRepo<CryptoSignalDbContext>(ctx);

/// <inheritdoc cref="UserRepo"/>
public sealed class LoginHistoryRepo(CryptoSignalDbContext ctx)
    : BaseLoginHistoryRepo<CryptoSignalDbContext>(ctx);
