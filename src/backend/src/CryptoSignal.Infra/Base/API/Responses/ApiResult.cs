using Microsoft.AspNetCore.Mvc;
using Newtonsoft.Json;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Extensions.Type;

namespace CryptoSignal.Infra.Base.API.Responses;

public class ApiResult
{
    public bool IsSuccess { get; set; }
    public ApiResultStatusCode StatusCode { get; set; }

    [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
    public string Message { get; set; }

    public ApiResult(bool isSuccess, ApiResultStatusCode statusCode, string? message = null)
    {
        IsSuccess = isSuccess;
        StatusCode = statusCode;
        Message = message ?? statusCode.ToDisplay();
    }

    #region Implicit Operators
    public static implicit operator ApiResult(OkResult result)
    {
        return new ApiResult(true, ApiResultStatusCode.Success);
    }

    public static implicit operator ApiResult(BadRequestResult result)
    {
        return new ApiResult(false, ApiResultStatusCode.BadRequest);
    }

    public static implicit operator ApiResult(BadRequestObjectResult result)
    {
        var message = result.Value?.ToString();
        if (result.Value is SerializableError errors)
        {
            var errorMessages = errors.SelectMany(p => (string[])p.Value).Distinct();
            message = string.Join(" | ", errorMessages);
        }
        return new ApiResult(false, ApiResultStatusCode.BadRequest, message);
    }

    public static implicit operator ApiResult(ContentResult result)
    {
        return new ApiResult(true, ApiResultStatusCode.Success, result.Content);
    }

    public static implicit operator ApiResult(NotFoundResult result)
    {
        return new ApiResult(false, ApiResultStatusCode.NotFound);
    }
    public static implicit operator ApiResult(UnauthorizedResult result)
    {
        return new ApiResult(false, ApiResultStatusCode.Unauthorized);
    }
    #endregion
}

public class ApiResult<TData>(bool isSuccess, ApiResultStatusCode statusCode, TData data, string message = null)
    : ApiResult(isSuccess, statusCode, message)
{
    [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
    public TData? Data { get; set; } = data;

    #region Implicit Operators
    public static implicit operator ApiResult<TData>(TData data)
    {
        return new ApiResult<TData>(true, ApiResultStatusCode.Success, data);
    }

    public static implicit operator ApiResult<TData>(OkResult result)
    {
        return new ApiResult<TData>(true, ApiResultStatusCode.Success, default);
    }

    public static implicit operator ApiResult<TData>(OkObjectResult result)
    {
        return new ApiResult<TData>(true, ApiResultStatusCode.Success, (TData)result.Value);
    }

    public static implicit operator ApiResult<TData>(BadRequestResult result)
    {
        return new ApiResult<TData>(false, ApiResultStatusCode.BadRequest, default);
    }

    public static implicit operator ApiResult<TData>(BadRequestObjectResult result)
    {
        var message = result.Value?.ToString();
        if (result.Value is SerializableError errors)
        {
            var errorMessages = errors.SelectMany(p => (string[])p.Value).Distinct();
            message = string.Join(" | ", errorMessages);
        }
        return new ApiResult<TData>(false, ApiResultStatusCode.BadRequest, default, message);
    }

    public static implicit operator ApiResult<TData>(ContentResult result)
    {
        return new ApiResult<TData>(true, ApiResultStatusCode.Success, default, result.Content);
    }

    public static implicit operator ApiResult<TData>(NotFoundResult result)
    {
        return new ApiResult<TData>(false, ApiResultStatusCode.NotFound, default);
    }

    public static implicit operator ApiResult<TData>(NotFoundObjectResult result)
    {
        return new ApiResult<TData>(false, ApiResultStatusCode.NotFound, (TData)result.Value);
    }

    #endregion
}
