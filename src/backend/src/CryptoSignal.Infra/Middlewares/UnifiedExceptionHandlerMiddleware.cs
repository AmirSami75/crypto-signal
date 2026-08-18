using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Hosting;
using Newtonsoft.Json;
using CryptoSignal.Infra.Base.API;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Abstract;
using CryptoSignal.Infra.Tooling.Logging.Adapters;

namespace CryptoSignal.Infra.Middlewares;

public class UnifiedExceptionHandlerMiddleware(
    RequestDelegate next,
    IWebHostEnvironment env,
    ILoggerAdapter<UnifiedExceptionHandlerMiddleware> logger)
{
    public async Task Invoke(HttpContext context)
    {
        try
        {
            await next(context);
        }
        catch (BaseException exception)
        {
            logger.Error(exception, "API Error: {ErrorCode} - {UserMessage}", exception.ErrorCode,
                exception.UserMessage!);

            await WriteErrorResponseAsync(
                context,
                statusCode: (int)exception.StatusCode,
                apiStatus: exception.StatusCode,
                message: GetMessage(exception),
                additionalData: exception.AdditionalData
            );
        }
        catch (UnauthorizedAccessException exception)
        {
            logger.Warning("Unauthorized access attempt.", exception);

            await WriteErrorResponseAsync(
                context,
                statusCode: StatusCodes.Status401Unauthorized,
                apiStatus: ApiResultStatusCode.Unauthorized,
                message: GetMessage(exception)
            );
        }
        catch (Exception exception)
        {
            logger.Error(exception, "Unhandled Exception");

            await WriteErrorResponseAsync(
                context,
                statusCode: StatusCodes.Status500InternalServerError,
                apiStatus: ApiResultStatusCode.ServerError,
                message: GetMessage(exception)
            );
        }
    }

    private string GetMessage(Exception exception)
    {
        if (env.IsDevelopment())
        {
            var dic = new Dictionary<string, object?>
            {
                ["Exception"] = exception.Message,
                ["StackTrace"] = exception.StackTrace,
            };

            if (exception.InnerException != null)
            {
                dic.Add("InnerException.Exception", exception.InnerException.Message);
                dic.Add("InnerException.StackTrace", exception.InnerException.StackTrace);
            }

            if (exception is BaseException baseEx && baseEx.AdditionalData != null)
                dic.Add("AdditionalData", baseEx.AdditionalData);

            return JsonConvert.SerializeObject(dic, Formatting.Indented);
        }
        else
        {
            if (exception is BaseException baseEx && !string.IsNullOrEmpty(baseEx.UserMessage))
                return baseEx.UserMessage;

            return "An error occurred while processing your request.";
        }
    }

    private async Task WriteErrorResponseAsync(
        HttpContext context,
        int statusCode,
        ApiResultStatusCode apiStatus,
        string message,
        object? additionalData = null)
    {
        if (context.Response.HasStarted)
            throw new InvalidOperationException(
                "The response has already started, the error handling middleware will not be executed.");

        var result =
            new ApiResult(false, apiStatus, message); // Optionally, add AdditionalData property to ApiResult if desired

        var json = JsonConvert.SerializeObject(result);

        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/json";
        await context.Response.WriteAsync(json);
    }
}