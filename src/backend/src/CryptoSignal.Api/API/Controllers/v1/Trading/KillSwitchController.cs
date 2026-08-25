using Asp.Versioning;
using CryptoSignal.Api.Application.DTOs.Trading;
using CryptoSignal.Api.Application.Trading.Abstractions;
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
/// The emergency stop: engage a switch and no new order intent is authorized within its scope.
/// </summary>
/// <remarks>
/// <para>
/// <b>Engaging blocks new intents. It does not cancel resting orders and it does not close positions.</b>
/// That restraint is deliberate and it is the single most important thing to understand about this
/// controller. Cancelling a working stop-loss would leave an open position unprotected, and liquidating
/// positions would make the emergency stop the riskiest button on the platform — it would place market
/// orders, at once, across every bot, in whatever conditions caused the operator to reach for it.
/// Stopping the flow of new trades is what an operator actually needs; unwinding is a separate,
/// deliberate act (<c>docs/LIVE_TRADING_SAFETY.md</c>).
/// </para>
/// <para>
/// Engaging is treated as the safe action throughout: its rate limit is loose, and it needs no
/// preconditions beyond a reason. Disengaging is the dangerous direction — it is what resumes trading —
/// so it is a separate permission and demands its own reason on the record.
/// </para>
/// </remarks>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("KillSwitch", "کلید توقف اضطراری")]
public class KillSwitchController(
    IRepo<KillSwitch> switches,
    IRepo<TradingBot> bots,
    IBotAuditTrail audit) : BaseController
{
    /// <summary>Switches, engaged first, then newest. History is kept rather than deleted.</summary>
    [HttpGet]
    [Permission(PermissionType.Get)]
    public async Task<ApiResult<PagedResult<KillSwitchDto>>> Get(
        CancellationToken ct,
        [FromQuery] bool? engagedOnly = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 50)
    {
        pageNumber = Math.Max(1, pageNumber);
        pageSize = Math.Clamp(pageSize, 1, 200);

        var query = switches.TableNoTracking;

        if (engagedOnly is true)
            query = query.Where(row => row.IsEngaged);

        var total = await query.CountAsync(ct);

        var page = await query
            .OrderByDescending(row => row.IsEngaged)
            .ThenByDescending(row => row.CreatedAt)
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);

        return Ok(new PagedResult<KillSwitchDto>(
            page.Select(Project).ToList(), total, pageNumber, pageSize));
    }

    /// <summary>
    /// Engages a switch. Takes effect on the next tick of every bot in scope.
    /// </summary>
    /// <remarks>
    /// Idempotent by design: engaging an already-engaged switch of the same scope returns the existing
    /// row instead of creating a second one. An operator hitting the button twice in an emergency must
    /// not have to reason about how many switches they now have to clear.
    /// </remarks>
    [HttpPost]
    [EnableRateLimiting(RateLimitPolicies.KillSwitchControl)]
    [Permission(PermissionType.Custom, nameof(Engage), "فعال سازی کلید توقف اضطراری")]
    public async Task<ApiResult<KillSwitchDto>> Engage(
        [FromBody] KillSwitchInputDto dto,
        CancellationToken ct)
    {
        if (dto is null)
            throw new BadRequestException("بدنه درخواست الزامی است");

        if (string.IsNullOrWhiteSpace(dto.Reason))
            throw new BadRequestException("ثبت دلیل توقف اضطراری الزامی است");

        var symbol = string.IsNullOrWhiteSpace(dto.ScopeSymbol)
            ? null
            : dto.ScopeSymbol.Trim().ToUpperInvariant();

        // A scoped switch with no scope value would read as that scope but cover nothing — the most
        // dangerous possible failure for this control, because the operator's dashboard would show a
        // switch engaged while every bot kept trading.
        switch (dto.Scope)
        {
            case KillSwitchScope.OperatingMode when dto.ScopeOperatingMode is null:
                throw new BadRequestException("برای توقف در سطح حالت اجرا، حالت اجرا الزامی است");

            case KillSwitchScope.Exchange when dto.ScopeVenue is null:
                throw new BadRequestException("برای توقف در سطح صرافی، صرافی الزامی است");

            case KillSwitchScope.Bot when dto.ScopeBotId is null:
                throw new BadRequestException("برای توقف در سطح ربات، شناسه ربات الزامی است");

            case KillSwitchScope.Symbol when symbol is null:
                throw new BadRequestException("برای توقف در سطح نماد، نماد الزامی است");
        }

        if (dto.ScopeBotId.HasValue)
        {
            var exists = await bots.TableNoTracking.AnyAsync(bot => bot.Id == dto.ScopeBotId.Value, ct);

            if (!exists)
                throw new NotFoundException("ربات مورد نظر یافت نشد");
        }

        var existing = await switches.Table.FirstOrDefaultAsync(
            row => row.IsEngaged
                   && row.Scope == dto.Scope
                   && row.ScopeOperatingMode == dto.ScopeOperatingMode
                   && row.ScopeVenue == dto.ScopeVenue
                   && row.ScopeBotId == dto.ScopeBotId
                   && row.ScopeSymbol == symbol,
            ct);

        if (existing is not null)
            return Ok(Project(existing));

        var (userId, _, userName, _, _, _, _, _, _) = GetUserInfo();

        var killSwitch = new KillSwitch
        {
            Scope = dto.Scope,
            ScopeOperatingMode = dto.ScopeOperatingMode,
            ScopeVenue = dto.ScopeVenue,
            ScopeBotId = dto.ScopeBotId,
            ScopeSymbol = symbol,
            IsEngaged = true,
            Reason = dto.Reason.Trim(),

            // Operator-engaged, so not automatic. The distinction matters when reviewing: an automatic
            // switch is the platform reacting to its own limits, and a manual one is a human decision.
            IsAutomatic = false,
            EngagedAt = DateTime.UtcNow,
            EngagedByUserId = userId,
            EngagedByUserName = userName,
        };

        await switches.AddAsync(killSwitch, saveNow: true, ct);

        await audit.AppendAsync(
            new BotAuditEntry(
                CorrelationId: Guid.CreateVersion7().ToString("N"),
                EventType: BotAuditEventType.KillSwitchBlocked,
                OperatingMode: dto.ScopeOperatingMode ?? OperatingMode.Paper,
                Summary: $"کلید توقف اضطراری در سطح {dto.Scope} فعال شد",
                BotId: dto.ScopeBotId,
                Detail: new { killSwitch.Scope, killSwitch.Reason, Symbol = symbol },
                KillSwitchId: killSwitch.Id,
                Symbol: symbol,
                ActorUserId: userId,
                ActorUserName: userName),
            ct);

        return Ok(Project(killSwitch));
    }

    /// <summary>
    /// Disengages a switch, allowing bots in its scope to be evaluated again.
    /// </summary>
    /// <remarks>
    /// This is the direction that resumes trading, so it carries its own permission and requires a reason
    /// even though engaging one already did. Both actors are recorded on the row: an incident review
    /// needs to know who stopped the platform and, separately, who decided it was safe to continue.
    /// </remarks>
    [HttpPost("{id:guid}/disengage")]
    [EnableRateLimiting(RateLimitPolicies.KillSwitchControl)]
    [Permission(PermissionType.Custom, nameof(Disengage), "غیرفعال سازی کلید توقف اضطراری")]
    public async Task<ApiResult<KillSwitchDto>> Disengage(
        Guid id,
        [FromBody] BotStatusChangeDto? dto,
        CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(dto?.Reason))
            throw new BadRequestException("ثبت دلیل غیرفعال سازی کلید توقف اضطراری الزامی است");

        var killSwitch = await switches.Table.FirstOrDefaultAsync(row => row.Id == id, ct)
                         ?? throw new NotFoundException("کلید توقف اضطراری مورد نظر یافت نشد");

        if (!killSwitch.IsEngaged)
            throw new BadRequestException("این کلید از قبل غیرفعال است");

        var (userId, _, userName, _, _, _, _, _, _) = GetUserInfo();

        killSwitch.IsEngaged = false;
        killSwitch.DisengagedAt = DateTime.UtcNow;
        killSwitch.DisengagedByUserId = userId;
        killSwitch.DisengagedByUserName = userName;

        // Appended to the reason rather than replacing it: the original reason is why trading stopped,
        // and overwriting it would erase the incident in the act of closing it.
        killSwitch.TriggerDetail = string.IsNullOrWhiteSpace(killSwitch.TriggerDetail)
            ? $"غیرفعال سازی: {dto.Reason.Trim()}"
            : $"{killSwitch.TriggerDetail} | غیرفعال سازی: {dto.Reason.Trim()}";

        await switches.UpdateAsync(killSwitch, saveNow: true, ct);

        await audit.AppendAsync(
            new BotAuditEntry(
                CorrelationId: Guid.CreateVersion7().ToString("N"),
                EventType: BotAuditEventType.ConfigurationChanged,
                OperatingMode: killSwitch.ScopeOperatingMode ?? OperatingMode.Paper,
                Summary: $"کلید توقف اضطراری در سطح {killSwitch.Scope} غیرفعال شد",
                BotId: killSwitch.ScopeBotId,
                Detail: new { Reason = dto.Reason.Trim() },
                KillSwitchId: killSwitch.Id,
                Symbol: killSwitch.ScopeSymbol,
                ActorUserId: userId,
                ActorUserName: userName),
            ct);

        return Ok(Project(killSwitch));
    }

    private static KillSwitchDto Project(KillSwitch row) => new(
        row.Id,
        row.Scope,
        row.ScopeOperatingMode,
        row.ScopeVenue,
        row.ScopeBotId,
        row.ScopeSymbol,
        row.IsEngaged,
        row.Reason,
        row.IsAutomatic,
        row.TriggerDetail,
        row.EngagedAt,
        row.EngagedByUserName,
        row.DisengagedAt,
        row.DisengagedByUserName,
        row.CreatedAt);
}
