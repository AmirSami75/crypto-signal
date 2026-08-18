using Asp.Versioning;
using MapsterMapper;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Application.DTOs.Permissions;
using CryptoSignal.Auth.Application.DTOs.Users;
using CryptoSignal.Auth.Domain.Constants;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Helpers;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;
using System.Data;
using CryptoSignal.Auth.Adapter.Query_Specifications.User;
using CryptoSignal.Auth.API.Attributes;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.RulesEngine;

namespace CryptoSignal.Auth.API.Controllers.v1;

/// <summary>
/// سرویس مدیریت سطوح دسترسی
/// </summary>
/// <param name="repo"></param>
/// <param name="mapper"></param>
/// <param name="searchFilter"></param>
/// <param name="logger"></param>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("Permission", "سطوح دسترسی")]
public sealed class PermissionController(
    IPermissionRepo repo,
    IRolePermissionRepo rolePermissionRepo,
    IMapperAdapter mapper,
    PermissionQuerySpecification searchFilter,
    ILoggerAdapter<PermissionController> logger,
    ICrudRuleExecutor<object, Permission, Guid> crudRules)
    : CrudController<PermissionController, object, PermissionOutputDto, PermissionSearchDto, Permission, Guid>(repo,
        mapper, searchFilter, logger,crudRules)
{
    const string PermissionDocumentFileName = "Permissions_Documents.pdf";
    const string PermissionFolderName = "Docs";

    /// <summary>
    /// راهنما سطوح دسترسی
    /// </summary>
    [HttpGet("[action]")]
    [Permission(PermissionType.Get)]
    public ApiResult<string> GetDocument()
    {
        var path = $"{AppDomain.CurrentDomain.BaseDirectory}{PermissionFolderName}/{PermissionDocumentFileName}";

        if (!System.IO.File.Exists(path))
            throw new LogicException("فایل راهنما بر روی سرور یافت نشد");

        var fileBytes = System.IO.File.ReadAllBytes(path);
        return new ApiResult<string>(true, ApiResultStatusCode.Success, Convert.ToBase64String(fileBytes));
    }

    /// <summary>
    /// سرویس دریافت اطلاعات سطوح دسترسی نقش های سیستم
    /// </summary>
    /// <param name="roleIds">لیست نقش هایی که سوح دسترسی آنها را نیاز دارید</param>
    /// <param name="ct"></param>
    /// <returns></returns>
    [HttpPost("resolve")]
    [Authorize]
    public async Task<ApiResult<List<string>>> FetchPermissionsByRoleIds(List<Guid> roleIds, CancellationToken ct)
        => await (from pr in rolePermissionRepo.TableNoTracking
                join p in repo.TableNoTracking on pr.PermissionId equals p.Id
                where roleIds.Contains(pr.RoleId)
                select p.Name)
            .ToListAsync(cancellationToken: ct);


    [NonAction]
    public override Task<ApiResult<PermissionOutputDto?>> Create(object dto, CancellationToken ct)
    {
        throw new NotImplementedException();
    }

    [NonAction]
    public override Task<ApiResult<PermissionOutputDto?>> Update(Guid id, object dto,
        CancellationToken cancellationToken)
    {
        throw new NotImplementedException();
    }

    [NonAction]
    public override Task<ApiResult> Delete(Guid id, CancellationToken ct)
    {
        throw new NotImplementedException();
    }

    [NonAction]
    public override Task<ApiResult<PermissionOutputDto>> Get(Guid id, CancellationToken ct)
    {
        throw new NotImplementedException();
    }
}