using Asp.Versioning;
using MapsterMapper;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Auth.Application.DTOs.Users;
using CryptoSignal.Auth.Domain.Constants;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.API.SearchFilter;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Extensions.Auth;
using CryptoSignal.Infra.Extensions.DB;
using CryptoSignal.Infra.Helpers;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;
using System.Data;
using System.Security.Claims;
using CryptoSignal.Infra.Base.API.SearchFilter;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Infra.Extensions.DB;
using CryptoSignal.Infra.RulesEngine;

namespace CryptoSignal.Auth.API.Controllers.v1;

[ApiVersion("1")]
public abstract class BaseUserController<TController, TInputDto, TOutputDto, TSearchDto, TUserEntity>(
    IBaseUserRepo<TUserEntity> repo,
    IUserRoleRepo userRoleRepo,
    IMapperAdapter mapper,
    ExpressionSearchFilterQuery<TUserEntity, TSearchDto> searchFilter,
    ILoggerAdapter<TController> logger,
    ICrudRuleExecutor<TInputDto, TUserEntity, Guid> crudRules)
    : CrudController<TController, TInputDto, TOutputDto, TSearchDto, TUserEntity, Guid>(repo, mapper, searchFilter,
        logger, crudRules)
    where TController : class
    where TInputDto : BaseUserInputDto
    where TOutputDto : BaseUserOutputDto<TUserEntity, TOutputDto>
    where TSearchDto : BaseUserSearchDto
    where TUserEntity : BaseUser
{
    #region Hook

    protected virtual void BeforeCreate(TInputDto dto, TUserEntity entity, CancellationToken ct)
    {
    }

    protected virtual void BeforeUpdate(TInputDto dto, TUserEntity entity, CancellationToken ct)
    {
    }

    #endregion

    /// <summary>
    /// فعالسازی حساب کاربر
    /// </summary>
    /// <param name="userId"></param>
    /// <param name="ct"></param>
    /// <returns></returns>
    [HttpPut("[action]")]
    [Permission(PermissionType.Custom, nameof(AccountActivation), "فعالسازی حساب کاربری")]
    public virtual async Task<ApiResult> AccountActivation(Guid userId, CancellationToken ct)
    {
        var user = await
        (
            from u in repo.TableNoTracking
            where u.Id == userId
            select u
        ).FirstOrDefaultAsync(ct);

        if (user is null)
            throw new NotFoundException();

        if (user.UserName == AuthGlobalVariables.DefaultUser)
            throw new LogicException("مجوز فعالسازی حساب کاربری سیستمی وجود ندارد");

        user.IsActive = true;
        user.IsLocked = false;
        user.FailedLoginAttempts = 0;
        user.SecurityStamp = Guid.NewGuid();

        await repo.UpdateAsync(user, cancellationToken: ct);

        Logger.Info($"حساب کاربری {user.UserName} فعال گردید");

        return Ok();
    }

    /// <summary>
    /// غیر فعالسازی حساب کاربر
    /// </summary>
    /// <param name="userId"></param>
    /// <param name="ct"></param>
    /// <returns></returns>
    [HttpPut("[action]")]
    [Permission(PermissionType.Custom, nameof(AccountDeActivation), "غیرفعالسازی حساب کاربری")]
    public virtual async Task<ApiResult> AccountDeActivation(Guid userId, CancellationToken ct)
    {
        var user = await
        (
            from u in repo.TableNoTracking
            where u.Id == userId
            select u
        ).FirstOrDefaultAsync(ct);

        if (user is null)
            throw new NotFoundException();

        if (user.UserName == AuthGlobalVariables.DefaultUser)
            throw new LogicException("مجوز غیرفعالسازی حساب کاربری سیستمی وجود ندارد");

        user.IsActive = false;
        user.IsLocked = false;
        user.FailedLoginAttempts = 0;
        user.SecurityStamp = Guid.NewGuid();

        await repo.UpdateAsync(user, cancellationToken: ct);

        Logger.Info($"حساب کاربری {user.UserName} غیرفعال گردید");

        return Ok();
    }

    /// <summary>
    /// بازیابی کلمه عبور کاربر به کلمه عبور پیشفرض
    /// </summary>
    /// <param name="userId"></param>
    /// <param name="ct"></param>
    /// <returns></returns>
    [HttpPut("[action]")]
    [Permission(PermissionType.Custom, nameof(ResetPassword), "بازیابی کلمه عبور کاربر به کلمه عبور پیشفرض")]
    public virtual async Task<ApiResult> ResetPassword(Guid userId, CancellationToken ct)
    {
        var user = await repo.Table
            .Include(p => p.UserRoles)
            .SingleOrDefaultAsync(p => p.Id == userId, ct);

        if (user is null)
            throw new NotFoundException();

        if (user.UserName == AuthGlobalVariables.DefaultUser)
            throw new LogicException("مجوز بازیابی کلمه عبور حساب کاربری سیستمی وجود ندارد");

        user.Password = PasswordHasher.Hash(AuthGlobalVariables.DefaultPassword);
        user.RequirePasswordChange = true;
        user.LastPasswordChangedAt = null;
        user.FailedLoginAttempts = 0;
        user.IsLocked = false;
        user.SecurityStamp = Guid.NewGuid();

        await repo.UpdateAsync(user, cancellationToken: ct);
        Logger.Info($"کلمه عبور کاربر {user.UserName} به کلمه عبور پیشفرض به روزرسانی گردید");
        return Ok();
    }

    public override async Task<ApiResult<TOutputDto?>> Create(TInputDto dto, CancellationToken ct)
    {
        // Check Dupplicate UserName
        if (await repo.TableNoTracking.AnyAsync(p => p.UserName == dto.UserName && !p.IsDeleted, cancellationToken: ct))
            throw new LogicException("نام کاربری وارد شده متعلق به کاربر دیگری است");

        // Check Dupplicate PersonelCode
        if (!string.IsNullOrWhiteSpace(dto.PersonelCode))
        {
            if (await repo.TableNoTracking.AnyAsync(p => p.PersonelCode == dto.PersonelCode && !p.IsDeleted,
                    cancellationToken: ct))
                throw new LogicException("کد پرسنلی وارد شده متعلق به کاربر دیگری است");
        }

        await using var transaction = await repo.DbContext.Database.BeginTransactionAsync(ct);

        try
        {
            // Add User
            var model = Mapper.Map<TUserEntity>(dto);
            BeforeCreate(dto, model, ct);
            model.UserCreatedId = base.User.Identity!.GetUserId<Guid>();
            model.UserCreatedName = base.User.Identity!.FindFirstValue(ClaimTypes.GivenName);
            model.Password = PasswordHasher.Hash(AuthGlobalVariables.DefaultPassword);
            await repo.AddAsync(model, cancellationToken: ct);

            await AddUserRoles(model.Id, dto.Roles);

            await transaction.CommitAsync(ct);

            var projected = await Project(BaseQuery.Where(p => p.Id.Equals(model.Id)))
                .SingleOrDefaultAsync(cancellationToken: ct);

            if (projected is null)
                throw new NotFoundException();

            var reMapped = Mapper.Remap(projected);

            Logger.Info($"کاربر جدیدی با نام کاربری {dto.UserName} ایجاد گردید");

            return reMapped;
        }
        catch (LogicException)
        {
            await transaction.RollbackAsync(ct);
            throw;
        }
        catch (Exception exp)
        {
            await transaction.RollbackAsync(ct);
            throw new LogicException("خطا در ایجاد کاربر", exp);
        }
    }

    public override async Task<ApiResult<TOutputDto?>> Update(Guid id, TInputDto dto, CancellationToken ct)
    {
        var user = await repo.Table
            .Include(p => p.UserRoles)
            .SingleOrDefaultAsync(p => p.Id == id, ct);

        if (user is null)
            throw new NotFoundException();

        if (user.UserName == AuthGlobalVariables.DefaultUser)
            throw new LogicException("مجوز ویرایش حساب کاربر سیستمی وجود ندارد");

        if (await repo.TableNoTracking.AnyAsync(
                p => p.UserName == dto.UserName && p.Id != id && !p.IsDeleted, ct))
            throw new LogicException("نام کاربری وارد شده متعلق به کاربر دیگری است");

        if (!string.IsNullOrWhiteSpace(dto.PersonelCode))
            if (await repo.TableNoTracking.AnyAsync(
                    p => p.PersonelCode == dto.PersonelCode && p.Id != id && !p.IsDeleted, ct))
                throw new LogicException("کد پرسنلی وارد شده متعلق به کاربر دیگری است");


        if (dto.ParentId != null)
        {
            if (id == dto.ParentId)
                throw new LogicException("کاربر بالادستی نمی تواند همان کاربر جاری باشد");

            var parent =
                await repo.TableNoTracking.FirstOrDefaultAsync(p => p.Id == dto.ParentId && p.IsDeleted == false, ct);
            if (parent is null)
                throw new LogicException("کاربر بالادستی  یافت نشد");

            if (parent.ParentId == id)
                throw new LogicException(
                    $"کاربر جاری به عنوان کاربر بالادستی در کاربر {parent.FullName} انتخاب شده است و کاربر {parent.FullName} نمی تواند کاربر بالادستی کاربر جاری انتخاب شود ");
        }


        await using var transaction = await repo.DbContext.Database.BeginTransactionAsync(ct);
        try
        {
            // Update User
            user = Mapper.MapInto(dto, user);
            BeforeUpdate(dto, user, ct);
            user.Id = id;
            user.UpdatedAt = DateTime.UtcNow;
            user.UserLastUpdatedId = base.User.Identity!.GetUserId<Guid>();
            user.UserLastUpdateName = base.User.Identity!.FindFirstValue(ClaimTypes.GivenName);

            await repo.UpdateAsync(user, false, ct);

            // Delete Old Roles
            var oldUserRoles = await userRoleRepo.Table
                .Where(p => p.UserId == user.Id)
                .ToListAsync(ct);
            if (oldUserRoles.Count > 0)
                await userRoleRepo.HardDeleteRangeAsync(oldUserRoles, false, ct);

            await AddUserRoles(user.Id, dto.Roles);

            await transaction.CommitAsync(ct);

            Logger.Info($"تغییرات بر روی موجودیت فعال با نام کاربری {dto.UserName} در سامانه با موفقیت ثبت گردید");

            var projected = await Project(BaseQuery.Where(p => p.Id.Equals(user.Id)))
                .SingleOrDefaultAsync(cancellationToken: ct);

            if (projected is null)
                throw new NotFoundException();

            var reMapped = Mapper.Remap(projected);

            return reMapped;
        }
        catch (LogicException)
        {
            await transaction.RollbackAsync(ct);
            throw;
        }
        catch (Exception exp)
        {
            await transaction.RollbackAsync(ct);
            throw new LogicException("خطا در ویرایش کاربر", exp);
        }
    }

    public override async Task<ApiResult> Delete(Guid id, CancellationToken ct)
    {
        var user = await repo.Table
            .SingleOrDefaultAsync(p => p.Id == id, ct);

        if (user is null)
            throw new NotFoundException();

        if (user.UserName == AuthGlobalVariables.DefaultUser)
            throw new LogicException("مجوز حذف حساب کاربری سیستمی وجود ندارد");

        return await base.Delete(id, ct);
    }

    protected abstract Task AddUserRoles(Guid userId, List<RolesIdsDto> roleIds);
}