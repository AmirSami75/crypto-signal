using Asp.Versioning;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Query_Specifications.User;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Extensions.Auth;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;
using System.Security.Claims;
using CryptoSignal.Infra.RulesEngine;

namespace CryptoSignal.Auth.API.Controllers.v1;

/// <summary>
/// سرویس مدیریت نقش
/// </summary>
/// <param name="repo"></param>
/// <param name="rolePermissionRepo"></param>
/// <param name="userRoleRepo"></param>
/// <param name="mapper"></param>
/// <param name="searchFilter"></param>
/// <param name="logger"></param>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("Role", "نقش")]
public sealed class RoleController(
    IRoleRepo repo,
    IRolePermissionRepo rolePermissionRepo,
    IUserRoleRepo userRoleRepo,
    IMapperAdapter mapper,
    RoleQuerySpecification searchFilter,
    ILoggerAdapter<RoleController> logger,
    ICrudRuleExecutor<RoleInputDto, Role, Guid> crudRules)
    : CrudController<RoleController, RoleInputDto, RoleOutputDto, RoleSearchDto, Role, Guid>(repo,
        mapper, searchFilter, logger, crudRules)
{
    public override async Task<ApiResult<RoleOutputDto?>> Create(RoleInputDto dto, CancellationToken ct)
    {
        if (dto.Permissions.Count == 0)
            throw new LogicException("هیچ مجوز دسترسی برای این نقش انتخاب نشده است");

        await using var transaction = await repo.DbContext.Database.BeginTransactionAsync(ct);
        try
        {
            var exists = await repo.DbContext.Set<Role>()
                .AnyAsync(r => r.Name == dto.Name && !r.IsDeleted, ct);

            if (exists)
                throw new LogicException("نام نقش تکراری می باشد.");

            var model = Mapper.Map<Role>(dto);
            // Add Role
            model.Type = RoleType.Custom;
            model.IsDeleted = false;
            model.UserCreatedId = base.User.Identity!.GetUserId<Guid>();
            model.UserCreatedName = base.User.Identity!.FindFirstValue(ClaimTypes.GivenName);

            await repo.AddAsync(model, cancellationToken: ct);

            var rolePermissions =
                dto.Permissions
                    .Select(permission => new RolePermission
                    {
                        PermissionId = permission.Id,
                        RoleId = model.Id,
                        UserCreatedId = base.User.Identity!.GetUserId<Guid>(),
                        UserCreatedName = base.User.Identity!.FindFirstValue(ClaimTypes.GivenName)
                    }).ToList();

            await rolePermissionRepo.AddRangeAsync(rolePermissions, cancellationToken: ct);


            await transaction.CommitAsync(ct);

            var projected = await Project(BaseQuery.Where(p => p.Id.Equals(model.Id)))
                .SingleOrDefaultAsync(cancellationToken: ct);

            if (projected is null)
                throw new NotFoundException();

            var reMapped = Mapper.Remap(projected);

            Logger.Info($"نقش با شناسه {dto?.Id} با موفقیت ایجاد گردید");

            return reMapped;
        }
        catch (LogicException ex)
        {
            await transaction.RollbackAsync(ct);
            throw;
        }
        catch (Exception exp)
        {
            await transaction.RollbackAsync(ct);
            throw new LogicException("خطا در ایجاد نقش");
        }
    }

    public override async Task<ApiResult<RoleOutputDto?>> Update(Guid id, RoleInputDto dto,
        CancellationToken cancellationToken)
    {
        if (dto.Permissions.Count == 0)
            throw new LogicException("هیچ مجوز دسترسی برای این نقش انتخاب نشده است");

        await using var transaction = await repo.DbContext.Database.BeginTransactionAsync(cancellationToken);
        try
        {
            var model = await repo.Table.SingleOrDefaultAsync(p => p.Id.Equals(id), cancellationToken);
            if (model is null)
                throw new NotFoundException();

            if (model.Type is RoleType.SuperAdmin or RoleType.User)
                throw new LogicException("شما مجوز ویرایش نقش های پیشفرض سیستم را ندارید");


            var exists = await repo.DbContext.Set<Role>()
                .AnyAsync(r => r.Name == dto.Name && r.Id != id && !r.IsDeleted, cancellationToken);

            if (exists)
                throw new LogicException("نام نقش تکراری می باشد.");

            model.Name = dto.Name;
            model.Title = dto.Title;
            model.IsDeleted = false;

            model.UpdatedAt = DateTime.UtcNow;
            model.UserLastUpdatedId = base.User.Identity!.GetUserId<Guid>();
            model.UserLastUpdateName = base.User.Identity!.FindFirstValue(ClaimTypes.GivenName);
            // Update Role
            await repo.UpdateAsync(model, false, cancellationToken);

            // Remove Old RolePermission
            var oldRolePermissions = rolePermissionRepo.Table.Where(p => p.RoleId == model.Id);
            await rolePermissionRepo.HardDeleteRangeAsync(oldRolePermissions, false, cancellationToken);

            // Add New RolePermission
            var newRolePermissions = dto.Permissions
                .Select(permission => new RolePermission
                {
                    RoleId = model.Id,
                    PermissionId = permission.Id
                }).ToList();

            await rolePermissionRepo.AddRangeAsync(newRolePermissions, cancellationToken: cancellationToken);

            await transaction.CommitAsync(cancellationToken);

            var projected = await Project(BaseQuery.Where(p => p.Id.Equals(model.Id)))
                .SingleOrDefaultAsync(cancellationToken: cancellationToken);

            if (projected is null)
                throw new NotFoundException();

            var reMapped = Mapper.Remap(projected);

            Logger.Info($"نقش با شناسه {reMapped?.Id} با موفقیت ایجاد گردید");

            return reMapped;
        }
        catch (LogicException)
        {
            await transaction.RollbackAsync(cancellationToken);
            throw;
        }
        catch (Exception exp)
        {
            await transaction.RollbackAsync(cancellationToken);
            throw new LogicException("خطا در ویرایش نقش");
        }
    }

    public override async Task<ApiResult> Delete(Guid id, CancellationToken ct)
    {
        var model = await repo.GetByIdAsync(ct, id);
        if (model is null)
            throw new NotFoundException();

        if (model.Type is RoleType.SuperAdmin or RoleType.User)
            throw new LogicException("شما مجوز حذف نقش های پیشفرض سیستم را ندارید");

        await using var transaction = await repo.DbContext.Database.BeginTransactionAsync(ct);
        try
        {
            // Remove RolePermission
            var rolePermissions = rolePermissionRepo.Table.Where(p => p.RoleId == model.Id);
            await rolePermissionRepo.HardDeleteRangeAsync(rolePermissions, false, ct);

            // Remove UserRole
            var userRoles = userRoleRepo.Table.Where(p => p.RoleId == id);
            await userRoleRepo.HardDeleteRangeAsync(userRoles, false, ct);

            // Delete Role
            await repo.HardDeleteAsync(model, cancellationToken: ct);

            await transaction.CommitAsync(ct);
            return Ok();
        }
        catch (LogicException)
        {
            await transaction.RollbackAsync(ct);
            throw;
        }
        catch (Exception exp)
        {
            await transaction.RollbackAsync(ct);
            throw new LogicException("خطا در حذف نقش");
        }
    }
}