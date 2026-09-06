using Asp.Versioning;
using CryptoSignal.Api.Domain.Constants;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Common;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.API.Controllers.v1.Trading;

/// <summary>
/// Market scanner: the newest strategy-zoo signals, ranked by <c>|24h change| × log10(volume)</c>.
/// </summary>
/// <remarks>
/// Signals are proposals only — nothing here places, cancels, or authorizes an order.
/// A scanner-kind bot claims a signal atomically inside <c>BotTickExecutor</c> and then walks the
/// same risk-gated pipeline as every other bot. The promote endpoint returns the bot
/// configuration the signal implies; creating and starting that bot stays on BotController,
/// where the operator is the one who pulls the trigger.
/// </remarks>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("Scanner", "اسکنر بازار")]
[EnableRateLimiting(RateLimitPolicies.BotControl)]
public class ScannerController(IRepo<ScannerSignal> signals) : BaseController
{
    /// <summary>The newest unclaimed signals, most-recent first, with simple filters.</summary>
    [HttpGet]
    [Permission(PermissionType.Get)]
    public async Task<ApiResult<PagedResult<ScannerSignalDto>>> Get(
        CancellationToken ct,
        [FromQuery] string? interval = null,
        [FromQuery] string? strategy = null,
        [FromQuery] SignalDirection? direction = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 50)
    {
        pageNumber = Math.Max(1, pageNumber);
        pageSize = Math.Clamp(pageSize, 1, 200);

        var query = signals.TableNoTracking.Where(s => s.TakenByBotId == null);

        if (!string.IsNullOrWhiteSpace(interval))
            query = query.Where(s => s.Interval == interval);

        if (!string.IsNullOrWhiteSpace(strategy))
            query = query.Where(s => s.StrategyKey == strategy);

        if (direction.HasValue)
            query = query.Where(s => s.Direction == direction.Value);

        var total = await query.CountAsync(ct);
        var items = await query
            .OrderByDescending(s => s.SignalCreatedAt)
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .Select(s => new ScannerSignalDto(
                s.Id, s.Symbol, s.Interval, s.StrategyKey, s.Direction, s.Confidence,
                s.Score, s.AtrAtSignal, s.SignalCreatedAt, s.Reason))
            .ToListAsync(ct);

        return Ok(new PagedResult<ScannerSignalDto>(items, total, pageNumber, pageSize));
    }

    /// <summary>
    /// One signal's implied scanner-bot configuration, for the dashboard's create form.
    /// The bot is NOT created here and nothing is traded; the operator reviews and submits it
    /// through the ordinary bot-creation path, which keeps the human gate before anything runs.
    /// </summary>
    [HttpGet("{signalId:guid}/promote")]
    [Permission(PermissionType.Get)]
    public async Task<ApiResult<PromoteScannerBotDto>> Promote(
        CancellationToken ct,
        Guid signalId)
    {
        var signal = await signals.TableNoTracking
            .FirstOrDefaultAsync(s => s.Id == signalId, ct);

        if (signal is null)
            throw new NotFoundException("سیگنال اسکنر مورد نظر یافت نشد");

        return Ok(new PromoteScannerBotDto(
            SuggestedName(signal),
            SuggestedIntervalBracket(signal),
            signal.Symbol,
            signal.Interval,
            signal.StrategyKey,
            signal.Direction,
            signal.Confidence,
            signal.AtrAtSignal));
    }

    /// <summary>A readable default name, e.g. "scanner BTCUSDT rsi 5m".</summary>
    private static string SuggestedName(ScannerSignal signal) =>
        $"scanner {signal.Symbol} {signal.StrategyKey} {signal.Interval}".Trim();

    /// <summary>
    /// Bracket from the signal's ATR: TP 1.5×ATR, SL 1.0×ATR, expressed as percent of a
    /// representative entry near the current price. Percent form keeps the existing bot
    /// pipeline unchanged; a scanner bot can still override with ATR multiples after creation.
    /// </summary>
    private static (decimal TakeProfitPercent, decimal StopLossPercent) SuggestedIntervalBracket(
        ScannerSignal signal)
    {
        // The signal does not carry the entry price; percent-of-price is approximated from the
        // ATR alone using a 4% reference price floor so the suggested percent never explodes on
        // low-priced symbols. The operator sees and can edit both numbers before starting.
        var referencePrice = Math.Max(1m, signal.AtrAtSignal * 25m);
        var takeProfit = Math.Round(signal.AtrAtSignal * 1.5m / referencePrice * 100m, 3);
        var stopLoss = Math.Round(signal.AtrAtSignal * 1.0m / referencePrice * 100m, 3);
        return (Math.Max(0.1m, takeProfit), Math.Max(0.1m, stopLoss));
    }
}

/// <summary>One scanner signal for the dashboard.</summary>
public sealed record ScannerSignalDto(
    Guid Id,
    string Symbol,
    string Interval,
    string StrategyKey,
    SignalDirection Direction,
    double Confidence,
    decimal Score,
    decimal AtrAtSignal,
    DateTimeOffset CreatedAt,
    string Reason);

/// <summary>The bot configuration a scanner signal implies, for pre-filling BotFormModal.</summary>
public sealed record PromoteScannerBotDto(
    string SuggestedName,
    (decimal TakeProfitPercent, decimal StopLossPercent) SuggestedBracket,
    string Symbol,
    string Interval,
    string StrategyKey,
    SignalDirection Direction,
    double Confidence,
    decimal AtrAtSignal);
