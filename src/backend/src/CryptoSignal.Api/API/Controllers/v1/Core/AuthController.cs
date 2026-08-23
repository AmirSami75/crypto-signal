using Asp.Versioning;
using CryptoSignal.Api.Adapter.Repos.Contracts.Auth;
using CryptoSignal.Api.Application.DTOs.Auth;
using CryptoSignal.Api.Domain.Constants;
using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.API.Controllers.v1;
using CryptoSignal.Auth.Application.Services.Contracts;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Helpers;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.API.Controllers.v1.Core;

/// <summary>
/// Authentication: registration, login, logout, password change and session validation.
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
    // Held in explicit fields instead of being captured from the primary constructor: the same
    // instances are already forwarded to the base constructor, and capturing them too would
    // duplicate that state (CS9107, an error here because the repository default sets
    // TreatWarningsAsErrors). A field initializer reads the parameter without capturing it.
    private readonly ILoginHistoryRepo _loginHistoryRepo = loginHistoryRepo;
    private readonly ILoggerAdapter<AuthController> _logger = logger;

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
    /// ثبت‌نام کاربر جدید — حساب ایجاد شده تا زمان تایید مدیر سامانه غیرفعال است
    /// </summary>
    /// <remarks>
    /// <para>
    /// Registration lives on this concrete controller rather than on
    /// <see cref="BaseAuthController{TController,TUserEntity,TLoginHistoryEntity,TLoginDto,TChangePasswordDto,TSessionUserDto}"/>
    /// because the policy it encodes — which defaults a new account gets, which roles it may hold,
    /// whether self-registration is open at all — is specific to this application rather than to
    /// the shared auth surface.
    /// </para>
    /// <para>
    /// Two properties make this endpoint safe to expose anonymously. It grants no access: the
    /// account is created inactive with no roles, and <c>Login</c> rejects an inactive user, so no
    /// token is returned here and none could be used if it were. And it grants no privilege: the
    /// payload it binds (<see cref="RegisterDto"/>) has no role, user-type or parent field to
    /// bind, so a caller cannot elevate itself by adding properties to the request body. An
    /// administrator activates the account through <c>PUT /api/v1/user/account-activation</c>.
    /// </para>
    /// <para>
    /// Deliberately carries no <c>[Permission]</c> attribute: <c>PermissionSeeder</c> mints a
    /// permission row for every action that has one, and an anonymous endpoint must not appear in
    /// the permission catalogue.
    /// </para>
    /// </remarks>
    /// <exception cref="LogicException">The username is already registered.</exception>
    [HttpPost("[action]")]
    [AllowAnonymous]
    [EnableRateLimiting(RateLimitPolicies.Registration)]
    public async Task<ApiResult> Register(RegisterDto dto, CancellationToken ct)
    {
        var userName = dto.UserName.Trim();

        // Mirrors the filter on UX_Users_UserName_Active: a soft-deleted account does not
        // permanently reserve its username.
        var isTaken = await repo.TableNoTracking
            .AnyAsync(u => u.UserName == userName && !u.IsDeleted, ct);

        if (isTaken)
            throw new LogicException("این نام کاربری قبلا ثبت شده است");

        var user = new User
        {
            FullName = dto.FullName.Trim(),
            UserName = userName,
            Email = string.IsNullOrWhiteSpace(dto.Email) ? null : dto.Email.Trim(),
            Mobile = string.IsNullOrWhiteSpace(dto.Mobile) ? null : dto.Mobile.Trim(),
            Password = PasswordHasher.Hash(dto.Password),

            // Inert until an administrator activates it. This is what makes anonymous
            // registration safe rather than a self-service door into the platform.
            IsActive = false,

            // The user chose this password seconds ago; there is nothing to rotate. This differs
            // from an admin-created account, which starts on a shared default and must change it.
            RequirePasswordChange = false,

            // Never taken from the request. Roles and user type are an administrator's decision,
            // made after activation — and UserRoles is deliberately left empty.
            UserType = null,
        };

        try
        {
            await repo.AddAsync(user, cancellationToken: ct);
        }
        catch (DbUpdateException)
        {
            // The unique index caught a username that was free at the check above and taken by the
            // time this insert landed. Same message as the check, so the race is invisible.
            throw new LogicException("این نام کاربری قبلا ثبت شده است");
        }

        _logger.Info($"درخواست ثبت‌نام با نام کاربری {userName} ثبت شد و در انتظار تایید مدیر سامانه است");

        return new ApiResult(true, ApiResultStatusCode.Success,
            "ثبت‌نام شما با موفقیت انجام شد. حساب کاربری شما پس از تایید مدیر سامانه فعال خواهد شد");
    }

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
