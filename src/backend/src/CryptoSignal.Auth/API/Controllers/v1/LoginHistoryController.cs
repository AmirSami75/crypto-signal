using Asp.Versioning;
using HotChocolate.Authorization;
using Microsoft.AspNetCore.Mvc;
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
using CryptoSignal.Infra.Base.API.SearchFilter;
using CryptoSignal.Infra.Extensions.Auth;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using CryptoSignal.Auth.Application.DTOs.LoginHistory;
using CryptoSignal.Infra.RulesEngine;

namespace CryptoSignal.Auth.API.Controllers.v1;

/// <summary>
/// سرویس مدیریت تاریخچه ورود
/// </summary>
/// <param name="repo"></param>
/// <param name="rolePermissionRepo"></param>
/// <param name="userRoleRepo"></param>
/// <param name="mapper"></param>
/// <param name="searchFilter"></param>
/// <param name="logger"></param>
[ApiVersion("1")]
[Authorize]
[ControllerInfo("LoginHistory", "تاریخچه ورود")]
public sealed class LoginHistoryController(
    ILoginHistoryRepo repo,
    IMapperAdapter mapper,
    LoginHistoryQuerySpecification searchFilter,
    ILoggerAdapter<LoginHistoryController> logger,
    ICrudRuleExecutor<object, LoginHistory, Guid> crudRules)
    : CrudController<LoginHistoryController, object, LoginHistoryOutputDto, LoginHistorySearchDto, LoginHistory, Guid>(
        repo,
        mapper, searchFilter, logger, crudRules)
{
    public override Task<ApiResult<PagedResult<LoginHistoryOutputDto>>> Get([FromQuery] LoginHistorySearchDto dto,
        CancellationToken ct, int page = 1, int pageSize = 10, bool desc = true)
    {
        var userId = User.Identity?.GetUserId<Guid>();
        BaseQuery.Where(p => p.UserId == userId);
        return base.Get(dto, ct, page, pageSize, desc);
    }

    #region NoAction

    [NonAction]
    public override Task<ApiResult<LoginHistoryOutputDto?>> Create(object dto, CancellationToken ct)
    {
        throw new NotImplementedException();
    }

    [NonAction]
    public override Task<ApiResult<LoginHistoryOutputDto?>> Update(Guid id, object dto,
        CancellationToken cancellationToken)
    {
        return base.Update(id, dto, cancellationToken);
    }

    [NonAction]
    public override Task<ApiResult> Delete(Guid id, CancellationToken ct)
    {
        return base.Delete(id, ct);
    }

    [NonAction]
    public override Task<ApiResult<IList<LoginHistoryOutputDto>>> Get(CancellationToken ct)
    {
        return base.Get(ct);
    }

    [NonAction]
    public override Task<ApiResult<LoginHistoryOutputDto>> Get(Guid id, CancellationToken ct)
    {
        return base.Get(id, ct);
    }

    #endregion
}