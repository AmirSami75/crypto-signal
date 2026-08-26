using Microsoft.AspNetCore.Mvc;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;

namespace CryptoSignal.Api.API.Controllers.v1.Trading;

/// <summary>One OHLC candle shaped for charting.</summary>
public sealed record ChartCandleDto(
    DateTime OpenTime,
    decimal Open,
    decimal High,
    decimal Low,
    decimal Close);

/// <summary>
/// Read-only candle feed for dashboard charts.
///
/// Exists because the venue sends no CORS headers, so the browser cannot fetch klines directly —
/// and should not: routing through the API keeps one place that knows about venue quirks (the OHLC
/// sanitiser, the paging limits) instead of teaching the frontend each vendor's dialect. Charts are
/// presentation; this endpoint is deliberately thin over the same market-data sources bots use.
/// </summary>
[CustomAuthorize]
[ControllerInfo("MarketCharts", "نمودار بازار")]
[Route("api/v{version:apiVersion}/charts")]
public class MarketChartsController(IMarketDataSourceResolver marketData) : BaseController
{
    [HttpGet("{venue}/candles")]
    [Permission(PermissionType.Custom, nameof(GetCandles), "نمودار شمعی بازار")]
    public async Task<ApiResult<List<ChartCandleDto>>> GetCandles(
        CancellationToken ct,
        [FromRoute] string venue,
        [FromQuery] string symbol,
        [FromQuery] string interval = "1h",
        [FromQuery] int limit = 96)
    {
        if (!Enum.TryParse<MarketVenue>(venue, ignoreCase: true, out var parsedVenue))
            throw new BadRequestException($"unknown venue '{venue}'");

        // Charts need tens of candles, not the model's 300; cap so a stray client cannot ask a
        // paged source for unbounded pages.
        limit = Math.Clamp(limit, 10, 300);

        var window = await marketData
            .Resolve(parsedVenue)
            .GetClosedCandlesAsync(symbol, interval, limit, ct);

        return window
            .Select(c => new ChartCandleDto(c.OpenTime.UtcDateTime, c.Open, c.High, c.Low, c.Close))
            .ToList();
    }
}
