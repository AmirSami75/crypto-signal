using Asp.Versioning;
using CryptoSignal.Api.Application.DTOs.Trading;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Application.Trading.Risk;
using CryptoSignal.Api.Domain.Constants;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Exceptions.Common;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.API.Controllers.v1.Trading;

/// <summary>
/// Bot configuration and lifecycle: create, edit, and start / pause / stop.
/// </summary>
/// <remarks>
/// <para>
/// <b>No action here places an order.</b> Starting a bot makes it eligible for evaluation by
/// <c>BotSchedulerService</c>; the order path lives entirely inside that scheduler
/// (<c>docs/LIVE_TRADING_SAFETY.md</c>). The distinction matters operationally, not just
/// architecturally: an HTTP request can be replayed by a browser refresh or a retrying proxy, and a
/// start that is replayed is harmless where a submit that is replayed is a duplicate trade.
/// </para>
/// <para>
/// Configuration and authorization are separated deliberately. Creating and editing a bot validates only
/// internal coherence — a barrier must be positive, a cadence must be a real duration — and never
/// consults the platform's allowlists. <b>Those are checked at start</b>, because writing down an
/// intention is research and starting is the moment the platform is asked to act on it. Refusing to save
/// a draft for a symbol that is not yet enabled would remove the ability to prepare a bot before
/// enabling its market, without preventing a single order.
/// </para>
/// </remarks>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("Bot", "ربات معامله گر")]
public class BotController(
    IRepo<TradingBot> bots,
    IRepo<BotPosition> positions,
    IRepo<BotRun> runs,
    IKillSwitchGuard killSwitches,
    IBotAuditTrail audit,
    IOptions<TradingRiskOptions> risk) : BaseController
{
    /// <summary>Bots, newest first, optionally filtered by mode, status or symbol.</summary>
    [HttpGet]
    [Permission(PermissionType.Get)]
    public async Task<ApiResult<PagedResult<BotSummaryDto>>> Get(
        CancellationToken ct,
        [FromQuery] OperatingMode? operatingMode = null,
        [FromQuery] BotStatus? status = null,
        [FromQuery] string? symbol = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 20)
    {
        pageNumber = Math.Max(1, pageNumber);
        pageSize = Math.Clamp(pageSize, 1, 200);

        var query = bots.TableNoTracking;

        // Filtering by mode is the first-class case, not an afterthought: paper and sandbox bots share
        // this table but never share a portfolio, so an operator reading a mixed list is reading two
        // unrelated books at once.
        if (operatingMode.HasValue)
            query = query.Where(bot => bot.OperatingMode == operatingMode.Value);

        if (status.HasValue)
            query = query.Where(bot => bot.Status == status.Value);

        if (!string.IsNullOrWhiteSpace(symbol))
        {
            var needle = symbol.Trim().ToUpperInvariant();
            query = query.Where(bot => bot.Symbol == needle);
        }

        var total = await query.CountAsync(ct);

        var page = await query
            .OrderByDescending(bot => bot.CreatedAt)
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);

        var ids = page.Select(bot => bot.Id).ToList();

        // Aggregated per bot in one round trip rather than per row, and grouped in the database: a
        // listing of 200 bots must not become 400 queries.
        var openCounts = await positions.TableNoTracking
            .Where(position => ids.Contains(position.BotId) && position.Status == PositionStatus.Open)
            .GroupBy(position => position.BotId)
            .Select(group => new { BotId = group.Key, Count = group.Count() })
            .ToListAsync(ct);

        var realized = await positions.TableNoTracking
            .Where(position => ids.Contains(position.BotId))
            .GroupBy(position => position.BotId)
            .Select(group => new { BotId = group.Key, Pnl = group.Sum(position => position.RealizedPnl) })
            .ToListAsync(ct);

        var blocked = new HashSet<Guid>();

        foreach (var bot in page)
        {
            if ((await killSwitches.GetBlockingAsync(bot, ct)).Count > 0)
                blocked.Add(bot.Id);
        }

        var items = page
            .Select(bot => new BotSummaryDto
            {
                Id = bot.Id,
                Name = bot.Name,
                Symbol = bot.Symbol,
                Interval = bot.Interval,
                Venue = bot.Venue,
                OperatingMode = bot.OperatingMode,
                Status = bot.Status,
                StatusReason = bot.StatusReason,
                TakeProfitPercent = bot.TakeProfitPercent,
                StopLossPercent = bot.StopLossPercent,
                AllowShort = bot.AllowShort,
                Leverage = bot.Leverage,
                QuoteNotionalPerTrade = bot.QuoteNotionalPerTrade,
                CadenceSeconds = bot.CadenceSeconds,
                LastTickAt = bot.LastTickAt,
                LastEvaluatedCandleOpenTime = bot.LastEvaluatedCandleOpenTime,
                FaultedAt = bot.FaultedAt,
                CreatedAt = bot.CreatedAt,
                OpenPositionCount = openCounts.FirstOrDefault(x => x.BotId == bot.Id)?.Count ?? 0,
                RealizedPnl = realized.FirstOrDefault(x => x.BotId == bot.Id)?.Pnl ?? 0m,
                IsBlockedByKillSwitch = blocked.Contains(bot.Id),
            })
            .ToList();

        return Ok(new PagedResult<BotSummaryDto>(items, total, pageNumber, pageSize));
    }

    /// <summary>One bot with its current lease, open positions and realised P&amp;L.</summary>
    [HttpGet("{id:guid}")]
    [Permission(PermissionType.Custom, nameof(GetById), "مشاهده جزئیات ربات معامله گر")]
    public async Task<ApiResult<BotDetailDto>> GetById(Guid id, CancellationToken ct)
    {
        var bot = await Load(id, tracked: false, ct);

        var open = await positions.TableNoTracking
            .Where(position => position.BotId == id && position.Status == PositionStatus.Open)
            .OrderBy(position => position.OpenedAt)
            .ToListAsync(ct);

        var closed = await positions.TableNoTracking
            .Where(position => position.BotId == id && position.Status == PositionStatus.Closed)
            .ToListAsync(ct);

        var run = await runs.TableNoTracking
            .Where(x => x.BotId == id)
            .OrderByDescending(x => x.StartedAt)
            .FirstOrDefaultAsync(ct);

        var blocking = await killSwitches.GetBlockingAsync(bot, ct);

        return Ok(new BotDetailDto
        {
            Id = bot.Id,
            Name = bot.Name,
            Description = bot.Description,
            Symbol = bot.Symbol,
            Interval = bot.Interval,
            Venue = bot.Venue,
            OperatingMode = bot.OperatingMode,
            TakeProfitPercent = bot.TakeProfitPercent,
            StopLossPercent = bot.StopLossPercent,
            AllowShort = bot.AllowShort,
            Leverage = bot.Leverage,
            QuoteNotionalPerTrade = bot.QuoteNotionalPerTrade,
            MinimumConfidence = bot.MinimumConfidence,
            MaxHoldingPeriods = bot.MaxHoldingPeriods,
            CadenceSeconds = bot.CadenceSeconds,
            Status = bot.Status,
            StatusReason = bot.StatusReason,
            FaultedAt = bot.FaultedAt,
            LastEvaluatedCandleOpenTime = bot.LastEvaluatedCandleOpenTime,
            LastTickAt = bot.LastTickAt,
            MaxOrderNotional = bot.MaxOrderNotional,
            MaxPositionNotional = bot.MaxPositionNotional,
            MaxDailyLoss = bot.MaxDailyLoss,
            MaxDrawdown = bot.MaxDrawdown,
            MaxConcurrentPositions = bot.MaxConcurrentPositions,
            MaxOrdersPerDay = bot.MaxOrdersPerDay,
            MaxConsecutiveFailures = bot.MaxConsecutiveFailures,
            MaxSlippageBps = bot.MaxSlippageBps,
            ExpectedModelVersion = bot.ExpectedModelVersion,
            ExchangeConnectionId = bot.ExchangeConnectionId,
            CreatedAt = bot.CreatedAt,
            UpdatedAt = bot.UpdatedAt,
            CurrentRun = run is null ? null : Project(run),
            OpenPositions = open.Select(Project).ToList(),
            RealizedPnl = closed.Sum(position => position.RealizedPnl),
            ClosedPositionCount = closed.Count,
            IsBlockedByKillSwitch = blocking.Count > 0,
        });
    }

    /// <summary>Creates a bot in <c>Draft</c>. A draft is inert until it is started.</summary>
    [HttpPost]
    [Permission(PermissionType.Create)]
    public async Task<ApiResult<BotDetailDto>> Create([FromBody] BotInputDto dto, CancellationToken ct)
    {
        Validate(dto);

        var bot = new TradingBot
        {
            Name = dto.Name.Trim(),
            Description = dto.Description?.Trim(),
            Symbol = dto.Symbol.Trim().ToUpperInvariant(),
            Interval = dto.Interval.Trim(),
            Venue = dto.Venue,
            OperatingMode = dto.OperatingMode,
            TakeProfitPercent = dto.TakeProfitPercent,
            StopLossPercent = dto.StopLossPercent,
            AllowShort = dto.AllowShort,
            Leverage = dto.Leverage,
            QuoteNotionalPerTrade = dto.QuoteNotionalPerTrade,
            MinimumConfidence = dto.MinimumConfidence,
            MaxHoldingPeriods = dto.MaxHoldingPeriods,
            CadenceSeconds = dto.CadenceSeconds,
            MaxOrderNotional = dto.MaxOrderNotional,
            MaxPositionNotional = dto.MaxPositionNotional,
            MaxDailyLoss = dto.MaxDailyLoss,
            MaxDrawdown = dto.MaxDrawdown,
            MaxConcurrentPositions = dto.MaxConcurrentPositions,
            MaxOrdersPerDay = dto.MaxOrdersPerDay,
            MaxConsecutiveFailures = dto.MaxConsecutiveFailures,
            MaxSlippageBps = dto.MaxSlippageBps,
            ExpectedModelVersion = string.IsNullOrWhiteSpace(dto.ExpectedModelVersion)
                ? null
                : dto.ExpectedModelVersion.Trim(),
            ExchangeConnectionId = dto.ExchangeConnectionId,

            // Never Active on creation, whatever the caller sent. Starting is its own permission and its
            // own audited action; a bot that could be born running would bypass both.
            Status = BotStatus.Draft,
        };

        await bots.AddAsync(bot, saveNow: true, ct);
        await Record(bot, BotAuditEventType.ConfigurationChanged, "ربات ایجاد شد", ct);

        return await GetById(bot.Id, ct);
    }

    /// <summary>
    /// Replaces a bot's configuration. Mode, symbol and interval are immutable once set.
    /// </summary>
    /// <remarks>
    /// Those three identify what the bot's existing decisions, orders and positions were about. Editing
    /// them in place would leave a paper bot's fills attached to a sandbox bot, or BTC positions under a
    /// bot that now claims to trade ETH — a chain that no longer describes what happened. Create a new
    /// bot instead; the old one keeps its history.
    /// </remarks>
    [HttpPut("{id:guid}")]
    [Permission(PermissionType.Update)]
    public async Task<ApiResult<BotDetailDto>> Update(Guid id, [FromBody] BotInputDto dto, CancellationToken ct)
    {
        Validate(dto);

        var bot = await Load(id, tracked: true, ct);

        if (bot.Status is BotStatus.Active)
        {
            throw new BadRequestException(
                "ربات فعال را نمی توان ویرایش کرد؛ ابتدا آن را متوقف یا موقتا غیرفعال کنید");
        }

        var symbol = dto.Symbol.Trim().ToUpperInvariant();

        if (!string.Equals(symbol, bot.Symbol, StringComparison.Ordinal))
            throw new BadRequestException("تغییر نماد ربات مجاز نیست؛ ربات جدیدی بسازید");

        if (!string.Equals(dto.Interval.Trim(), bot.Interval, StringComparison.Ordinal))
            throw new BadRequestException("تغییر بازه زمانی ربات مجاز نیست؛ ربات جدیدی بسازید");

        if (dto.OperatingMode != bot.OperatingMode)
            throw new BadRequestException("تغییر حالت اجرای ربات مجاز نیست؛ ربات جدیدی بسازید");

        bot.Name = dto.Name.Trim();
        bot.Description = dto.Description?.Trim();
        bot.Venue = dto.Venue;
        bot.TakeProfitPercent = dto.TakeProfitPercent;
        bot.StopLossPercent = dto.StopLossPercent;
        bot.AllowShort = dto.AllowShort;
        bot.Leverage = dto.Leverage;
        bot.QuoteNotionalPerTrade = dto.QuoteNotionalPerTrade;
        bot.MinimumConfidence = dto.MinimumConfidence;
        bot.MaxHoldingPeriods = dto.MaxHoldingPeriods;
        bot.CadenceSeconds = dto.CadenceSeconds;
        bot.MaxOrderNotional = dto.MaxOrderNotional;
        bot.MaxPositionNotional = dto.MaxPositionNotional;
        bot.MaxDailyLoss = dto.MaxDailyLoss;
        bot.MaxDrawdown = dto.MaxDrawdown;
        bot.MaxConcurrentPositions = dto.MaxConcurrentPositions;
        bot.MaxOrdersPerDay = dto.MaxOrdersPerDay;
        bot.MaxConsecutiveFailures = dto.MaxConsecutiveFailures;
        bot.MaxSlippageBps = dto.MaxSlippageBps;
        bot.ExpectedModelVersion = string.IsNullOrWhiteSpace(dto.ExpectedModelVersion)
            ? null
            : dto.ExpectedModelVersion.Trim();
        bot.ExchangeConnectionId = dto.ExchangeConnectionId;

        await bots.UpdateAsync(bot, saveNow: true, ct);
        await Record(bot, BotAuditEventType.ConfigurationChanged, "تنظیمات ربات ویرایش شد", ct);

        return await GetById(bot.Id, ct);
    }

    /// <summary>
    /// Soft-deletes a stopped bot. Its decisions, orders and fills stay queryable.
    /// </summary>
    /// <remarks>
    /// An active bot cannot be deleted: the delete would make it invisible to this controller while the
    /// scheduler's own query decided independently whether to keep ticking it. Stopping first makes the
    /// halt explicit and auditable rather than a side effect of a row disappearing.
    /// </remarks>
    [HttpDelete("{id:guid}")]
    [Permission(PermissionType.Delete)]
    public async Task<ApiResult> Delete(Guid id, CancellationToken ct)
    {
        var bot = await Load(id, tracked: true, ct);

        if (bot.Status is BotStatus.Active or BotStatus.Paused)
            throw new BadRequestException("ابتدا ربات را متوقف کنید، سپس حذف نمایید");

        var openPositions = await positions.TableNoTracking
            .CountAsync(position => position.BotId == id && position.Status == PositionStatus.Open, ct);

        if (openPositions > 0)
        {
            throw new BadRequestException(
                $"این ربات {openPositions} پوزیشن باز دارد؛ حذف آن پوزیشن ها را رها می کند");
        }

        await bots.SoftDeleteAsync(bot, saveNow: true, ct);
        await Record(bot, BotAuditEventType.ConfigurationChanged, "ربات حذف شد", ct);

        return Ok();
    }

    /// <summary>
    /// Makes a bot eligible for evaluation. <b>This is the authorization moment</b>, so every platform
    /// gate is applied here.
    /// </summary>
    /// <remarks>
    /// The checks are a subset of the risk engine's, not a replacement for it: the engine re-runs them
    /// from one snapshot before any order, because config can change between a start and a tick. Their
    /// purpose here is to fail loudly at the moment an operator asks for something the platform will
    /// silently refuse forever — a bot that starts and then denies every intent looks broken rather than
    /// misconfigured.
    /// </remarks>
    [HttpPost("{id:guid}/start")]
    [EnableRateLimiting(RateLimitPolicies.BotControl)]
    [Permission(PermissionType.Custom, nameof(Start), "شروع ربات معامله گر")]
    public async Task<ApiResult<BotDetailDto>> Start(
        Guid id,
        [FromBody] BotStatusChangeDto? dto,
        CancellationToken ct)
    {
        var bot = await Load(id, tracked: true, ct);
        var limits = risk.Value;

        if (bot.Status is BotStatus.Active)
            throw new BadRequestException("این ربات از قبل فعال است");

        if (bot.Status is BotStatus.Faulted)
        {
            throw new BadRequestException(
                $"ربات در وضعیت خطا است و باید ابتدا متوقف شود: {bot.StatusReason ?? "بدون توضیح"}");
        }

        // Mode gate. An empty EnabledOperatingModes denies every mode — an unconfigured deployment runs
        // nothing rather than everything.
        if (!limits.EnabledOperatingModes.Contains(bot.OperatingMode.ToString(), StringComparer.OrdinalIgnoreCase))
        {
            throw new BadRequestException(
                $"حالت اجرای {bot.OperatingMode} در تنظیمات پلتفرم فعال نیست");
        }

        if (bot.OperatingMode is OperatingMode.Live && !limits.AllowLiveExecution)
            throw new BadRequestException("اجرای معاملات واقعی در این پلتفرم غیرفعال است");

        // Symbol gate — checked at start, not at create. Empty means nothing is tradable.
        if (!limits.AllowedSymbols.Contains(bot.Symbol, StringComparer.OrdinalIgnoreCase))
            throw new BadRequestException($"نماد {bot.Symbol} در فهرست نمادهای مجاز پلتفرم نیست");

        if (bot.AllowShort && (limits.SpotOnly || !limits.AllowShorting))
        {
            throw new BadRequestException(
                "این ربات مجاز به فروش استقراضی است، اما پلتفرم فقط معاملات نقدی را پشتیبانی می کند");
        }

        var futuresVenue = bot.Venue == MarketVenue.Bybit;
        if (bot.Leverage < 1 || (!futuresVenue && bot.Leverage != 1))
            throw new BadRequestException("اهرم باید برای بازارهای نقدی برابر 1 باشد و برای معاملات آتی حداقل 1 باشد");
        if (futuresVenue && (limits.SpotOnly || limits.MaxLeverage < bot.Leverage))
            throw new BadRequestException("اهرم در تنظیمات پلتفرم فعال نیست یا از سقف مجاز بیشتر است");

        // Fail-closed limits: zero denies, so a bot with a zero ceiling would start and then refuse
        // every single intent. Reporting that here is the difference between "misconfigured" and
        // "mysteriously idle".
        var zeroed = ZeroLimits(bot, limits);

        if (zeroed.Count > 0)
        {
            throw new BadRequestException(
                "این محدودیت ها صفر هستند و هر سفارش را رد می کنند: " + string.Join("، ", zeroed));
        }

        var blocking = await killSwitches.GetBlockingAsync(bot, ct);

        if (blocking.Count > 0)
        {
            throw new BadRequestException(
                "کلید توقف اضطراری فعال است و این ربات را پوشش می دهد: " +
                string.Join("، ", blocking.Select(switchRow => switchRow.Reason)));
        }

        return await Transition(bot, BotStatus.Active, dto?.Reason, "ربات فعال شد", ct);
    }

    /// <summary>
    /// Suspends evaluation without ending the bot's run or touching its positions.
    /// </summary>
    /// <remarks>
    /// Pause is the honest name: an open position stays open and its bracket stays working at the venue.
    /// Nothing here closes anything — that would make "pause" a market order, which is the last thing an
    /// operator reaching for it expects.
    /// </remarks>
    [HttpPost("{id:guid}/pause")]
    [EnableRateLimiting(RateLimitPolicies.BotControl)]
    [Permission(PermissionType.Custom, nameof(Pause), "توقف موقت ربات معامله گر")]
    public async Task<ApiResult<BotDetailDto>> Pause(
        Guid id,
        [FromBody] BotStatusChangeDto? dto,
        CancellationToken ct)
    {
        var bot = await Load(id, tracked: true, ct);

        if (bot.Status is not BotStatus.Active)
            throw new BadRequestException("فقط ربات فعال را می توان موقتا غیرفعال کرد");

        return await Transition(bot, BotStatus.Paused, dto?.Reason, "ربات موقتا غیرفعال شد", ct);
    }

    /// <summary>
    /// Stops the bot and closes its lease. Open positions are left as they are, deliberately.
    /// </summary>
    /// <remarks>
    /// Stopping means "evaluate nothing further", not "liquidate". Closing a position is a trade, and a
    /// trade belongs to the scheduler behind the risk engine — never to an HTTP handler. An operator who
    /// wants out of a position closes it as its own audited action.
    /// </remarks>
    [HttpPost("{id:guid}/stop")]
    [EnableRateLimiting(RateLimitPolicies.BotControl)]
    [Permission(PermissionType.Custom, nameof(Stop), "خاتمه ربات معامله گر")]
    public async Task<ApiResult<BotDetailDto>> Stop(
        Guid id,
        [FromBody] BotStatusChangeDto? dto,
        CancellationToken ct)
    {
        var bot = await Load(id, tracked: true, ct);

        if (bot.Status is BotStatus.Stopped)
            throw new BadRequestException("این ربات از قبل متوقف است");

        var open = await runs.Table
            .Where(run => run.BotId == bot.Id && run.EndedAt == null)
            .ToListAsync(ct);

        foreach (var run in open)
            run.EndedAt = DateTime.UtcNow;

        if (open.Count > 0)
            await runs.UpdateRangeAsync(open, saveNow: true, ct);

        // Clearing FaultedAt on the way out is what makes a faulted bot restartable: the fault is
        // preserved in the audit chain, and keeping it on the row as well would make "stop then start"
        // impossible without an operator editing the database.
        bot.FaultedAt = null;

        return await Transition(bot, BotStatus.Stopped, dto?.Reason, "ربات متوقف شد", ct);
    }

    #region Internals

    private async Task<TradingBot> Load(Guid id, bool tracked, CancellationToken ct)
    {
        var bot = await (tracked ? bots.Table : bots.TableNoTracking)
            .FirstOrDefaultAsync(row => row.Id == id, ct);

        return bot ?? throw new NotFoundException("ربات مورد نظر یافت نشد");
    }

    private async Task<ApiResult<BotDetailDto>> Transition(
        TradingBot bot,
        BotStatus status,
        string? reason,
        string summary,
        CancellationToken ct)
    {
        bot.Status = status;
        bot.StatusReason = string.IsNullOrWhiteSpace(reason) ? null : reason.Trim();

        await bots.UpdateAsync(bot, saveNow: true, ct);
        await Record(bot, BotAuditEventType.ConfigurationChanged, summary, ct);

        return await GetById(bot.Id, ct);
    }

    /// <summary>
    /// Appends the lifecycle event, attributed to the operator who made the request.
    /// </summary>
    /// <remarks>
    /// The correlation id is freshly minted rather than borrowed from a tick's: a configuration change
    /// is its own causal story, and folding it into the chain of a tick it did not cause would
    /// misattribute both. V7 so the chain sorts by creation time even across correlations.
    /// </remarks>
    private async Task Record(TradingBot bot, BotAuditEventType type, string summary, CancellationToken ct)
    {
        var (userId, _, userName, _, _, _, _, _, _) = GetUserInfo();

        await audit.AppendAsync(
            new BotAuditEntry(
                CorrelationId: Guid.CreateVersion7().ToString("N"),
                EventType: type,
                OperatingMode: bot.OperatingMode,
                Summary: summary,
                BotId: bot.Id,
                Detail: new { bot.Status, bot.StatusReason, bot.Symbol, bot.Interval, bot.Venue },
                Symbol: bot.Symbol,
                ActorUserId: userId,
                ActorUserName: userName),
            ct);
    }

    /// <summary>Names the limits that are zero, on the bot or on the platform ceiling above it.</summary>
    private static List<string> ZeroLimits(TradingBot bot, TradingRiskOptions limits)
    {
        var zeroed = new List<string>();

        void Check(string name, decimal bot_, decimal platform)
        {
            if (bot_ <= 0 || platform <= 0)
                zeroed.Add(name);
        }

        Check("حد سفارش", bot.MaxOrderNotional, limits.MaxOrderNotional);
        Check("حد پوزیشن", bot.MaxPositionNotional, limits.MaxPositionNotional);
        Check("حد ضرر روزانه", bot.MaxDailyLoss, limits.MaxDailyLoss);
        Check("سفارش در روز", bot.MaxOrdersPerDay, limits.MaxOrdersPerDay);
        Check("پوزیشن همزمان", bot.MaxConcurrentPositions, limits.MaxConcurrentPositions);

        if (bot.QuoteNotionalPerTrade <= 0)
            zeroed.Add("حجم هر معامله");

        if (limits.MaxCandleAgeIntervals <= 0)
            zeroed.Add("حد کهنگی کندل");

        return zeroed;
    }

    private static BotPositionDto Project(BotPosition position) => new(
        position.Id,
        position.OperatingMode,
        position.Venue,
        position.Symbol,
        position.Direction,
        position.Status,
        position.AverageEntryPrice,
        position.Quantity,
        position.EntryNotional,
        position.TakeProfitPrice,
        position.StopLossPrice,
        position.OpenedAt,
        position.ClosedAt,
        position.BarsHeld,
        position.AverageExitPrice,
        position.CloseReason,
        position.RealizedPnl,
        position.FeesPaid,
        position.UnrealizedPnl,
        position.LastMarkPrice,
        position.LastMarkedAt,
        position.MaxAdverseExcursion);

    private static BotRunDto Project(BotRun run) => new(
        run.Id,
        run.LeaseOwner,
        run.StartedAt,
        run.LastHeartbeatAt,
        run.EndedAt,
        run.TickCount,
        run.DecisionCount,
        run.OrderCount,
        run.ErrorCount,
        run.ConsecutiveFailureCount,
        run.LastError,
        run.LastErrorAt,
        run.LastTickAt);

    /// <summary>
    /// Internal coherence only. Allowlists are not consulted — see the remarks on the controller.
    /// </summary>
    private static void Validate(BotInputDto dto)
    {
        if (dto is null)
            throw new BadRequestException("بدنه درخواست الزامی است");

        if (string.IsNullOrWhiteSpace(dto.Name))
            throw new BadRequestException("نام ربات الزامی است");

        if (string.IsNullOrWhiteSpace(dto.Symbol))
            throw new BadRequestException("نماد ارز الزامی است");

        if (!CandleInterval.TryToTimeSpan(dto.Interval, out var interval))
            throw new BadRequestException($"بازه زمانی '{dto.Interval}' پشتیبانی نمی شود");

        if (dto.TakeProfitPercent <= 0)
            throw new BadRequestException("درصد حد سود باید بزرگتر از صفر باشد");

        if (dto.StopLossPercent <= 0)
            throw new BadRequestException("درصد حد ضرر باید بزرگتر از صفر باشد");

        if (dto.MinimumConfidence is < 0 or > 1)
            throw new BadRequestException("حداقل اطمینان باید بین صفر و یک باشد");

        if (dto.MaxHoldingPeriods < 0)
            throw new BadRequestException("حداکثر تعداد کندل نگهداری نمی تواند منفی باشد");

        if (dto.CadenceSeconds < 5)
            throw new BadRequestException("فاصله بررسی ربات نمی تواند کمتر از ۵ ثانیه باشد");

        // A cadence far shorter than the interval buys nothing and costs a request per tick: the model's
        // answer cannot change until a new candle closes, because the answer is computed from closed
        // candles. Half the interval keeps a bot responsive to a close without polling for its own sake.
        if (dto.CadenceSeconds > interval.TotalSeconds * 2)
        {
            throw new BadRequestException(
                "فاصله بررسی از دو برابر بازه کندل بیشتر است و ربات کندل ها را از دست می دهد");
        }

        if (dto.MaxSlippageBps < 0)
            throw new BadRequestException("حد لغزش قیمت نمی تواند منفی باشد");
    }

    #endregion
}
