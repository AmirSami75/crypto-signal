using Asp.Versioning;
using CryptoSignal.Api.Adapter.Repos.Contracts.Auth;
using CryptoSignal.Api.Application.DTOs.Auth;
using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.API.Controllers.v1;
using CryptoSignal.Auth.Application.Services.Contracts;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.API.Controllers.v1.Core;

/// <summary>
/// Authentication: login, logout, password change and session validation.
/// </summary>
[ApiVersion("1")]
[ControllerInfo("Auth", "احراز هویت")]
public class AuthController(
    IUserRepo repo,
    ILoginHistoryRepo loginHistoryRepo,
    IMapperAdapter mapper,
    ILoggerAdapter<AuthController> logger,
    IAuthService<User> authService)
    : BaseAuthController<AuthController, User, LoginHistory, LoginDto, ChangePasswordDto, SessionUserDto>(
        repo, loginHistoryRepo, mapper, logger, authService)
{
    // Held in an explicit field instead of being captured from the primary constructor: the same
    // instance is already forwarded to the base constructor, and capturing it too would duplicate
    // that state (CS9107). A field initializer reads the parameter without capturing it.
    private readonly ILoginHistoryRepo _loginHistoryRepo = loginHistoryRepo;

    #region Hooks

    /// <summary>
    /// Loads the login candidate together with the full role/permission graph. The base controller
    /// walks <c>UserRoles → Role → RolePermissions → Permission</c> to build the session, so every
    /// level has to be eager-loaded here.
    /// </summary>
    protected override Task<User?> FetchUserEntity(string userName, CancellationToken ct)
        => repo.Table
            .Include(u => u.UserRoles)
            .ThenInclude(ur => ur.Role)
            .ThenInclude(r => r.RolePermissions)!
            .ThenInclude(rp => rp.Permission)
            .FirstOrDefaultAsync(u => u.UserName == userName && !u.IsDeleted, ct);

    /// <summary>
    /// Supplies the <c>user_type</c> token claim.
    /// </summary>
    protected override async Task<string?> FetchUserType(Guid userId)
    {
        var userType = await repo.TableNoTracking
            .Where(u => u.Id == userId)
            .Select(u => u.UserType)
            .SingleOrDefaultAsync();

        return userType?.ToString();
    }

    #endregion

    /// <summary>
    /// Records a login attempt for audit purposes.
    /// </summary>
    protected override async Task AddLoginHistory(Guid userId, LoginStatus status, CancellationToken ct)
    {
        var history = new LoginHistory
        {
            UserId = userId,
            Ip = clientIpName,
            UserAgent = $"{clientOsName} {clientBrowserName}".Trim(),
            Status = status,
            LoginType = LoginType.Internal,
        };

        await _loginHistoryRepo.AddAsync(history, cancellationToken: ct);
    }
}
