using Asp.Versioning;
using CryptoSignal.Api.Application.DTOs.Trading;
using CryptoSignal.Api.Application.Trading.Reporting;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;
using Microsoft.AspNetCore.Mvc;

namespace CryptoSignal.Api.API.Controllers.v1.Trading;

/// <summary>
/// The reporting read side for one bot: a lumibot-style performance tearsheet.
/// </summary>
/// <remarks>
/// <para>
/// Read-only by construction — this controller depends only on <see cref="BotTearsheetService"/>,
/// which issues no-tracking SELECTs against existing tables and performs no writes. It lives apart
/// from <c>BotHistoryController</c> so the reporting shape can evolve without touching the audit
/// read side, but it shares the same route prefix so the URL reads as part of the bot resource:
/// <c>GET /api/v1/bot/{botId}/tearsheet</c>.
/// </para>
/// </remarks>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("BotTearsheet", "کارنامه ربات معامله گر")]
[Route("api/v{version:apiVersion}/bot/{botId:guid}")]
public class BotTearsheetController(BotTearsheetService tearsheets) : BaseController
{
    /// <summary>
    /// Performance summary for the last <paramref name="days"/> days (1–365, default 30).
    /// </summary>
    [HttpGet("tearsheet")]
    [Permission(PermissionType.Custom, nameof(GetTearsheet), "مشاهده کارنامه ربات معامله گر")]
    public async Task<ApiResult<BotTearsheetDto>> GetTearsheet(
        Guid botId,
        CancellationToken ct,
        [FromQuery] int days = 30)
    {
        days = Math.Clamp(days, 1, 365);
        return Ok(await tearsheets.GetAsync(botId, days, DateTime.UtcNow, ct));
    }
}
