using System.Net;
using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Extensions.Auth;

namespace CryptoSignal.Infra.Base.API.Controller;

[ApiController]
[Authorize]
//[AllowAnonymous]
[ApiResultFilter]
[Route("api/v{version:apiVersion}/[controller]")]
public abstract class BaseController : ControllerBase
{
    /// <summary>
    /// Retrieves the bearer token from the authorization header.
    /// </summary>
    /// <returns>The bearer token as a string.</returns>
    protected virtual string GetBearerTokenAsync()
    {
        var authorizationHeader = HttpContext.Request.Headers.Authorization.ToString();

        if (string.IsNullOrWhiteSpace(authorizationHeader))
            return string.Empty;

        const string bearerPrefix = "Bearer ";

        return authorizationHeader.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase)
            ? authorizationHeader[bearerPrefix.Length..].Trim()
            : string.Empty;
    }

    protected (Guid? userId, string? userFullName, string? userName, Guid? branchId, string? branchName, string?
        branchCode, string? userIp, string? superAdmin, string? userIsParent) GetUserInfo()
    {
        var claimsIdentity = HttpContext?.User.Identities.First();
        var userId = claimsIdentity?.GetUserId<Guid>();
        var userFullName = claimsIdentity?.FindFirstValue(ClaimTypes.GivenName);
        var userName = claimsIdentity?.FindFirstValue(ClaimTypes.Name);
        Guid.TryParse(claimsIdentity?.FindFirstValue("branch_id"), out Guid branchId);
        var branchName = claimsIdentity?.FindFirstValue("branch_name");
        var branchCode = claimsIdentity?.FindFirstValue("branch_code");
        var userIp = claimsIdentity?.FindFirstValue("client_ip");
        var superAdmin = claimsIdentity?.FindFirstValue("super_admin");
        var userIsParent = claimsIdentity?.FindFirstValue("parent_user");
        return (userId, userFullName, userName, branchId, branchName, branchCode, userIp, superAdmin, userIsParent);
    }

    #region Executors

    // ---------- 1) Pass-through: ApiResult<T> ----------
    protected static async Task<ApiResult<T>> Execute<T>(Func<Task<ApiResult<T>>> action)
    {
        try
        {
            return await action();
        }
        catch (LogicException ex)
        {
            throw new LogicException(ex.Message);
        }
        catch (Exception ex)
        {
            throw new Exception(ex.Message);
        }
    }

    // ---------- 2) Pass-through: ApiResult (non-generic) ----------
    protected static async Task<ApiResult> Execute(Func<Task<ApiResult>> action)
    {
        try
        {
            return await action();
        }
        catch (LogicException ex)
        {
            throw new LogicException(ex.Message);
        }
        catch (Exception ex)
        {
            throw new Exception(ex.Message);
        }
    }

    // ---------- 3) Auto-wrap: Task<T> -> ApiResult<T> ----------
    protected static async Task<ApiResult<T>> Execute<T>(
        Func<Task<T>> action,
        ApiResultStatusCode successCode = ApiResultStatusCode.Success,
        string? successMessage = null)
    {
        try
        {
            var data = await action();
            return new ApiResult<T>(true, successCode, data, successMessage);
        }
        catch (LogicException ex)
        {
            throw new LogicException(ex.Message);
        }
        catch (Exception ex)
        {
            throw new Exception(ex.Message);
        }
    }

    // ---------- 4) Auto-wrap: Task (void) -> ApiResult ----------
    protected static async Task<ApiResult> Execute(
        Func<Task> action,
        ApiResultStatusCode successCode = ApiResultStatusCode.Success,
        string? successMessage = null)
    {
        try
        {
            await action();
            return new ApiResult(true, successCode, successMessage);
        }
        catch (LogicException ex)
        {
            throw new LogicException(ex.Message);
        }
        catch (Exception ex)
        {
            throw new Exception(ex.Message);
        }
    }

    #endregion
}