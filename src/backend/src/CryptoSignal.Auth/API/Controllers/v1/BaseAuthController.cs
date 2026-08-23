using Asp.Versioning;
using MassTransit.Util;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Application.DTOs.Auth;
using CryptoSignal.Auth.Application.Services.Contracts;
using CryptoSignal.Auth.Domain.Constants;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Extensions.Auth;
using CryptoSignal.Infra.Helpers;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;

namespace CryptoSignal.Auth.API.Controllers.v1;

[ApiVersion("1")]
public abstract class BaseAuthController<TController, TUserEntity, TLoginHistoryEntity, TLoginDto, TChangePasswordDto,
    TSessionUserDto>(
    IBaseUserRepo<TUserEntity> repo,
    ILoginHistoryRepo loginHistoryRepo,
    IMapperAdapter mapper,
    ILoggerAdapter<TController> logger,
    IAuthService<TUserEntity> authService) : BaseController
    where TController : class
    where TUserEntity : BaseUser
    where TLoginDto : BaseLoginDto
    where TChangePasswordDto : BaseChangePasswordDto
    where TSessionUserDto : BaseSessionUserDto
{
    protected string? clientOsName = default;
    protected string? clientBrowserName = default;
    protected string? clientIpName = default;

    #region Hooks

    protected virtual Task<string?> FetchUserType(Guid userId) => Task.FromResult<string?>(null);

    protected abstract Task<TUserEntity?> FetchUserEntity(string userName, CancellationToken ct);

    #endregion

    /// <summary>
    /// لاگین کاربر 
    /// </summary>
    /// <param name="dto"></param>
    /// <param name="ct"></param>
    /// <returns></returns>
    /// <exception cref="NotFoundException"></exception>
    /// <exception cref="ForbiddenException"></exception>
    /// <exception cref="LogicException"></exception>
    [HttpPost("[action]")]
    [AllowAnonymous]
    public virtual async Task<ApiResult<TSessionUserDto>> Login(
        TLoginDto dto,
        CancellationToken ct)
    {
        // The connection's own remote address wins over the header, and the ordering is the security
        // control rather than a preference. `X-ClientIp` is set by the caller, so a client that wanted
        // to poison the audit trail could name any address it liked and the login-history row would
        // record it as fact. Reading the socket first means the recorded address is one the server
        // observed; the header survives only as a fallback for a deployment sitting behind a proxy
        // that rewrites the connection to a loopback address.
        //
        // A browser cannot discover its own public address, so before this the column was null for
        // every sign-in from the dashboard — the header the client would have to send is one it has no
        // way to fill in.
        clientIpName = HttpContext.Connection.RemoteIpAddress?.ToString();

        if (string.IsNullOrWhiteSpace(clientIpName) && Request.Headers.TryGetValue("X-ClientIp", out var clientIp))
            clientIpName = clientIp[0];

        if (Request.Headers.TryGetValue("X-ClientOS", out var clientOs))
            clientOsName = clientOs[0];

        if (Request.Headers.TryGetValue("X-ClientBrowser", out var clientBrowser))
            clientBrowserName = clientBrowser[0];

        var user = await FetchUserEntity(dto.UserName, ct);

        if (user is null)
            throw new NotFoundException("نام کاربری یا کلمه عبور نامعتبر است");
        if (!user.IsActive)
            throw new ForbiddenException(
                "کاربر گرامی حساب کاربری شما مسدود شده است لطفا با مدیر سامانه تماس حاصل فرمایید");
        if (user.IsLocked)
            throw new ForbiddenException(
                "کاربر گرامی حساب کاربری شما قفل شده است لطفا با مدیر سامانه تماس حاصل فرمایید");

        if (!PasswordHasher.Verify(dto.Password, user.Password))
        {
            var remainingNumberOfTimes = 0;
            user.FailedLoginAttempts += 1;
            remainingNumberOfTimes = AuthGlobalVariables.NumberOfWrongPasswordsAllowed - user.FailedLoginAttempts;

            if (user.FailedLoginAttempts == AuthGlobalVariables.NumberOfWrongPasswordsAllowed)
                user.IsLocked = true;

            await repo.UpdateAsync(user, cancellationToken: ct);

            if (remainingNumberOfTimes != 0)
                throw new LogicException("نام کاربری یا کلمه عبور نامعتبر است");

            // Login History
            await AddLoginHistory(user.Id, LoginStatus.Error, ct);

            throw new LogicException("کاربر گرامی حساب کاربری شما قفل شده است لطفا با مدیر سیستم تماس حاصل فرمایید");
        }

        var requiresChangePassword = authService.RequiresChangePassword(user);

        // Update Security Stamp
        user.SecurityStamp = Guid.NewGuid();
        user.FailedLoginAttempts = 0;
        user.RequirePasswordChange = requiresChangePassword;

        // Login History
        await AddLoginHistory(user.Id, LoginStatus.Success, ct);

        clientIpName = clientIpName ?? string.Empty;

        var userType = await FetchUserType(user.Id)!;

        var tokenDto = await authService.GenerateToken(user, clientIpName, requiresChangePassword, userType);

        await repo.UpdateAsync(user, cancellationToken: ct);

        // return Current User
        var sessionUser = mapper.Map<TSessionUserDto>(user);


        sessionUser.UserId = user.Id;
        sessionUser.FullName = user.FullName;
        sessionUser.UserName = user.UserName;
        sessionUser.Token = tokenDto.Token;
        sessionUser.TokenExpiry = tokenDto.ExpireDate;
        sessionUser.RequiresPasswordChange = requiresChangePassword;


        var roleIds = new List<Guid>();
        var permissionNames = new List<string>();
        var superAdmin = false;

        foreach (var userRole in user.UserRoles)
        {
            roleIds.Add(userRole.RoleId);
            if (userRole.Role.Type == RoleType.SuperAdmin)
                superAdmin = true;
        }

        foreach (var userRole in user.UserRoles)
            if (superAdmin is false)
                if (userRole.Role.RolePermissions != null)
                    foreach (var rolePermission in userRole.Role.RolePermissions)
                        if (rolePermission != null && rolePermission.Permission != null)
                            permissionNames.Add(rolePermission.Permission!.Name);


        sessionUser.IsSuperAdmin = superAdmin;
        sessionUser.Roles = roleIds;
        sessionUser.Permissions = permissionNames;


        logger.Info($"نشست کاربر با نام کاربری {dto.UserName} با موفقیت ایجاد گردید");
        logger.Info($"عملیات احراز هویت کاربر با نام کاربری {dto.UserName} با موفقیت انجام گردید");

        return sessionUser;
    }

    /// <summary>
    /// Change Password
    /// </summary>
    /// <param name="dto"></param>
    /// <param name="ct"></param>
    /// <returns></returns>
    [HttpPut("[action]")]
    [Authorize]
    public virtual async Task<ApiResult> ChangePassword(TChangePasswordDto dto, CancellationToken ct)
    {
        var userId = User?.Identity?.GetUserId<Guid>();

        var user = await repo.Table.FirstOrDefaultAsync(p => p.Id == userId, ct);

        if (user is null)
            throw new NotFoundException("کاربر یافت نشد");

        if (!PasswordHasher.Verify(dto.CurrentPass, user.Password))
            throw new LogicException("کلمه عبور نامعتبر است");

        if (PasswordHasher.Verify(dto.NewPass, user.Password))
            throw new LogicException("کلمه عبور جدید با کلمه عبور فعلی یکسان است");

        if (!user.IsActive)
            throw new LogicException("حساب کاربری شما فعال نیست");

        logger.Info(" کلمه عبور با الگو منطبق است");

        user.Password = PasswordHasher.Hash(dto.NewPass);
        user.SecurityStamp = Guid.NewGuid();
        user.RequirePasswordChange = false;
        user.LastPasswordChangedAt = DateTime.UtcNow;
        await repo.UpdateAsync(user, cancellationToken: ct);
        logger.Info("عملیات به روزرسانی کلمه عبور با موفقیت انجام گردید");
        return Ok();
    }
    
    /// <summary>
    /// Logout
    /// </summary>
    /// <param name="ct"></param>
    /// <returns></returns>
    /// <exception cref="NotFoundException"></exception>
    [HttpPost("[action]")]
    [Authorize]
    public virtual async Task<ApiResult> Logout(CancellationToken ct)
    {
        var userId = User?.Identity?.GetUserId<Guid>();
        var user = await repo.Table.FirstOrDefaultAsync(p => p.Id == userId, ct);
        if (user is null)
            throw new NotFoundException("کاربر یافت نشد");
        user.SecurityStamp = Guid.NewGuid();
        await repo.UpdateAsync(user, cancellationToken: ct);
        return Ok();
    }

    [HttpGet("session-validate")]
    [Authorize]
    public async Task<IActionResult> ValidateToken() => Ok(new { ok = true });

    protected abstract Task AddLoginHistory(Guid userId, LoginStatus status, CancellationToken ct);
}