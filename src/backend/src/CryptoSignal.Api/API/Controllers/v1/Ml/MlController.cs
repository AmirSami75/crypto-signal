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
/// Read-only access to the Python ML engine: its advertised capabilities and model metadata.
/// </summary>
/// <remarks>
/// Nothing here authorizes or places an order. A signal is evidence, not authorization — see
/// <c>docs/LIVE_TRADING_SAFETY.md</c> — and order submission happens only inside the bot scheduler,
/// never inside an HTTP request. Signals themselves live on <c>SignalController</c>, which carries its
/// own <c>Signal.*</c> permissions: inspecting the engine and asking it for a trade are different
/// privileges. Exceptions are thrown rather than returned so
/// <c>UnifiedExceptionHandlerMiddleware</c> renders the same envelope every other endpoint uses.
/// </remarks>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("Ml", "موتور یادگیری ماشین")]
public class MlController(IMlServiceClient mlService) : BaseController
{
    /// <summary>
    /// Capabilities advertised by the ML engine: the candle window it accepts, the markets it has
    /// models for, and whether the pooled cross-symbol model can answer everything else.
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
    /// Metadata for the model that answers a given market.
    /// </summary>
    /// <remarks>
    /// Leaving both parameters empty resolves the pooled model. The response reports which model
    /// actually answered via <c>isWildcard</c>, so a caller asking about a symbol with no dedicated
    /// model can tell that it was answered by the pooled one rather than assuming a bespoke fit.
    /// </remarks>
    [HttpGet("model")]
    [Permission(PermissionType.Custom, nameof(GetModel), "مشاهده اطلاعات مدل یادگیری ماشین")]
    public async Task<ApiResult<MlModelInfo>> GetModel(
        CancellationToken ct,
        [FromQuery] string? symbol = null,
        [FromQuery] string? interval = null)
    {
        var model = await mlService.GetModelInfoAsync(symbol ?? string.Empty, interval ?? string.Empty, ct);

        if (model is null)
            throw new ServiceUnavailableException("مدل یادگیری ماشین بارگذاری نشده است");

        return Ok(model);
    }
}
