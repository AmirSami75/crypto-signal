using Asp.Versioning;
using CryptoSignal.Api.Clients;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Common;
using Microsoft.AspNetCore.Mvc;

namespace CryptoSignal.Api.API.Controllers.v1.Ml;

/// <summary>
/// Read-only access to the Python ML engine: capabilities, model metadata and signal predictions.
/// </summary>
/// <remarks>
/// This controller does not authorize exchange orders — the orchestrator owns that decision.
/// Exceptions are thrown rather than returned so <c>UnifiedExceptionHandlerMiddleware</c> renders
/// the same envelope every other endpoint uses.
/// </remarks>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("Ml", "موتور یادگیری ماشین")]
public class MlController(IMlServiceClient mlService) : BaseController
{
    /// <summary>
    /// Capabilities advertised by the ML engine, including the candle-count window it accepts.
    /// </summary>
    [HttpGet("capabilities")]
    [Permission(PermissionType.Custom, nameof(GetCapabilities), "مشاهده قابلیت های موتور یادگیری ماشین")]
    public async Task<ApiResult<MlServiceCapabilities>> GetCapabilities(CancellationToken ct)
    {
        var capabilities = await mlService.GetCapabilitiesAsync(ct);

        if (capabilities is null)
            throw new ServiceUnavailableException("سرویس یادگیری ماشین در دسترس نیست");

        return Ok(capabilities);
    }

    /// <summary>
    /// Metadata for the model currently loaded by the ML engine.
    /// </summary>
    [HttpGet("model")]
    [Permission(PermissionType.Custom, nameof(GetModel), "مشاهده اطلاعات مدل یادگیری ماشین")]
    public async Task<ApiResult<MlModelInfo>> GetModel(CancellationToken ct)
    {
        var model = await mlService.GetModelInfoAsync(ct);

        if (model is null)
            throw new ServiceUnavailableException("مدل یادگیری ماشین بارگذاری نشده است");

        return Ok(model);
    }

    /// <summary>
    /// Requests a trading signal for a window of completed candles.
    /// </summary>
    /// <remarks>
    /// Only closed candles may be submitted; including the in-progress candle leaks future
    /// information into the features and invalidates the prediction.
    /// </remarks>
    [HttpPost("predictions")]
    [Permission(PermissionType.Custom, nameof(PredictSignal), "دریافت سیگنال از موتور یادگیری ماشین")]
    public async Task<ApiResult<MlPrediction>> PredictSignal(
        [FromBody] MlPredictionRequest request,
        CancellationToken ct)
    {
        if (request.Candles is null || request.Candles.Count == 0)
            throw new BadRequestException("ارسال حداقل یک کندل بسته شده الزامی است");

        try
        {
            var prediction = await mlService.PredictSignalAsync(request, ct);
            return Ok(prediction);
        }
        catch (MlServiceException exception) when (exception.ErrorCode == "InvalidArgument")
        {
            throw new BadRequestException(exception.Message);
        }
        catch (MlServiceException exception)
        {
            throw new ServiceUnavailableException(exception.Message);
        }
    }
}
