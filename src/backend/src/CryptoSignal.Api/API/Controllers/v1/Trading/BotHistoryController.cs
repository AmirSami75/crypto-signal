using Asp.Versioning;
using CryptoSignal.Api.Application.DTOs.Trading;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Base.Enums;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.API.Controllers.v1.Trading;

/// <summary>
/// The read side of a bot's causal chain: what it decided, what it tried to place, what the risk engine
/// said, what the venue did, and what filled.
/// </summary>
/// <remarks>
/// <para>
/// Entirely read-only, and separated from <c>BotController</c> because it answers a different question
/// with a different permission. Editing a bot and auditing one are different jobs: a reviewer should be
/// able to read every decision and every refusal without being able to start anything.
/// </para>
/// <para>
/// <b>Refusals are first-class here.</b> Denied intents and their <c>RiskDecision</c> rows are returned
/// alongside filled ones rather than filtered out — "why did the platform not place this trade" is the
/// first question an incident review asks, and a history showing only successes cannot answer it
/// (<c>docs/LIVE_TRADING_SAFETY.md</c>).
/// </para>
/// </remarks>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("BotHistory", "تاریخچه ربات معامله گر")]
[Route("api/v{version:apiVersion}/bot/{botId:guid}")]
public class BotHistoryController(
    IRepo<StrategyDecision> decisions,
    IRepo<OrderIntent> intents,
    IRepo<RiskDecision> riskDecisions,
    IRepo<ExchangeOrder> exchangeOrders,
    IRepo<OrderFill> fills,
    IRepo<BotPosition> positions,
    IRepo<BotAuditEvent> auditEvents) : BaseController
{
    /// <summary>
    /// Evaluations, newest first. One row per closed candle the bot acted on.
    /// </summary>
    /// <remarks>
    /// HOLD decisions are included. They are the majority and they are the evidence that the bot was
    /// alive and declining, which is materially different from the bot not having run.
    /// </remarks>
    [HttpGet("decisions")]
    [Permission(PermissionType.Custom, nameof(GetDecisions), "مشاهده تصمیم های ربات معامله گر")]
    public async Task<ApiResult<PagedResult<BotDecisionDto>>> GetDecisions(
        Guid botId,
        CancellationToken ct,
        [FromQuery] BotDecisionAction? action = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 50)
    {
        pageNumber = Math.Max(1, pageNumber);
        pageSize = Math.Clamp(pageSize, 1, 200);

        var query = decisions.TableNoTracking.Where(row => row.BotId == botId);

        if (action.HasValue)
            query = query.Where(row => row.Action == action.Value);

        var total = await query.CountAsync(ct);

        var page = await query
            .OrderByDescending(row => row.CandleOpenTime)
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);

        return Ok(new PagedResult<BotDecisionDto>(
            page.Select(Project).ToList(), total, pageNumber, pageSize));
    }

    /// <summary>
    /// Intents newest first, each with its risk verdict and any venue orders and fills beneath it.
    /// </summary>
    /// <remarks>
    /// Assembled in four queries rather than by navigation loading: the shape is a shallow tree over one
    /// page of intents, and letting EF walk it per row would issue a query per intent per level.
    /// </remarks>
    [HttpGet("orders")]
    [Permission(PermissionType.Custom, nameof(GetOrders), "مشاهده سفارش های ربات معامله گر")]
    public async Task<ApiResult<PagedResult<OrderIntentDto>>> GetOrders(
        Guid botId,
        CancellationToken ct,
        [FromQuery] OrderIntentStatus? status = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 50)
    {
        pageNumber = Math.Max(1, pageNumber);
        pageSize = Math.Clamp(pageSize, 1, 200);

        var query = intents.TableNoTracking.Where(row => row.BotId == botId);

        if (status.HasValue)
            query = query.Where(row => row.Status == status.Value);

        var total = await query.CountAsync(ct);

        var page = await query
            .OrderByDescending(row => row.CreatedAt)
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);

        var intentIds = page.Select(row => row.Id).ToList();

        var risk = await riskDecisions.TableNoTracking
            .Where(row => intentIds.Contains(row.OrderIntentId))
            .ToListAsync(ct);

        var orders = await exchangeOrders.TableNoTracking
            .Where(row => intentIds.Contains(row.OrderIntentId))
            .OrderBy(row => row.SubmittedAt)
            .ToListAsync(ct);

        var orderIds = orders.Select(row => row.Id).ToList();

        var orderFills = await fills.TableNoTracking
            .Where(row => orderIds.Contains(row.ExchangeOrderId))
            .OrderBy(row => row.ExecutedAt)
            .ToListAsync(ct);

        var items = page
            .Select(intent => Project(
                intent,
                risk.FirstOrDefault(row => row.OrderIntentId == intent.Id),
                orders.Where(row => row.OrderIntentId == intent.Id).ToList(),
                orderFills))
            .ToList();

        return Ok(new PagedResult<OrderIntentDto>(items, total, pageNumber, pageSize));
    }

    /// <summary>Positions, newest first — open and closed.</summary>
    [HttpGet("positions")]
    [Permission(PermissionType.Custom, nameof(GetPositions), "مشاهده پوزیشن های ربات معامله گر")]
    public async Task<ApiResult<PagedResult<BotPositionDto>>> GetPositions(
        Guid botId,
        CancellationToken ct,
        [FromQuery] PositionStatus? status = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 50)
    {
        pageNumber = Math.Max(1, pageNumber);
        pageSize = Math.Clamp(pageSize, 1, 200);

        var query = positions.TableNoTracking.Where(row => row.BotId == botId);

        if (status.HasValue)
            query = query.Where(row => row.Status == status.Value);

        var total = await query.CountAsync(ct);

        var page = await query
            .OrderByDescending(row => row.OpenedAt)
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);

        return Ok(new PagedResult<BotPositionDto>(
            page.Select(Project).ToList(), total, pageNumber, pageSize));
    }

    /// <summary>
    /// The audit chain for this bot, newest correlation first and in causal order within each.
    /// </summary>
    /// <remarks>
    /// Ordered by <c>OccurredAt</c> then <c>Sequence</c>, never by timestamp alone: several events from
    /// one tick land in the same millisecond, and a timestamp-only sort would show a fill before the
    /// order that produced it.
    /// </remarks>
    [HttpGet("audit")]
    [Permission(PermissionType.Custom, nameof(GetAudit), "مشاهده زنجیره حسابرسی ربات معامله گر")]
    public async Task<ApiResult<PagedResult<BotAuditEventDto>>> GetAudit(
        Guid botId,
        CancellationToken ct,
        [FromQuery] string? correlationId = null,
        [FromQuery] BotAuditEventType? eventType = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 100)
    {
        pageNumber = Math.Max(1, pageNumber);
        pageSize = Math.Clamp(pageSize, 1, 500);

        var query = auditEvents.TableNoTracking.Where(row => row.BotId == botId);

        if (!string.IsNullOrWhiteSpace(correlationId))
        {
            var needle = correlationId.Trim();
            query = query.Where(row => row.CorrelationId == needle);
        }

        if (eventType.HasValue)
            query = query.Where(row => row.EventType == eventType.Value);

        var total = await query.CountAsync(ct);

        var page = await query
            .OrderByDescending(row => row.OccurredAt)
            .ThenByDescending(row => row.Sequence)
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);

        return Ok(new PagedResult<BotAuditEventDto>(
            page.Select(Project).ToList(), total, pageNumber, pageSize));
    }

    #region Projections

    private static BotDecisionDto Project(StrategyDecision decision) => new(
        decision.Id,
        decision.BotId,
        decision.OperatingMode,
        decision.Symbol,
        decision.Interval,
        decision.CandleOpenTime,
        decision.CandleWindowDigest,
        decision.Action,
        decision.Direction,
        decision.ReasonCode,
        decision.Confidence,
        decision.LongConfidence,
        decision.ShortConfidence,
        decision.ExpectedValue,
        decision.ProbabilityTakeProfitFirst,
        decision.ProbabilityStopLossFirst,
        decision.ProbabilityTimeout,
        decision.EntryPrice,
        decision.TakeProfitPrice,
        decision.StopLossPrice,
        decision.Atr,
        decision.RiskRewardRatio,
        decision.ModelId,
        decision.ModelVersion,
        decision.ModelTrainedAt,
        decision.UsedWildcardModel,
        decision.BarrierExtrapolated,
        decision.Warning,
        decision.ValidUntil,
        decision.ProcessingMilliseconds,
        decision.CreatedAt);

    private static OrderIntentDto Project(
        OrderIntent intent,
        RiskDecision? risk,
        IReadOnlyList<ExchangeOrder> orders,
        IReadOnlyList<OrderFill> allFills) => new(
        intent.Id,
        intent.BotId,
        intent.StrategyDecisionId,
        intent.OperatingMode,
        intent.ClientOrderId,
        intent.Symbol,
        intent.Direction,
        intent.Side,
        intent.Type,
        intent.Quantity,
        intent.LimitPrice,
        intent.TakeProfitPrice,
        intent.StopLossPrice,
        intent.TimeInForce,
        intent.ReferencePrice,
        intent.EstimatedNotional,
        intent.Status,
        intent.StatusReason,
        intent.SubmittedAt,
        intent.CompletedAt,
        intent.CreatedAt,
        risk is null ? null : Project(risk),
        orders.Select(order => Project(order, allFills)).ToList());

    /// <summary>
    /// Splits the stored CSV back into check names.
    /// </summary>
    /// <remarks>
    /// An allowed decision stores an empty string, which <c>Split</c> would turn into a single empty
    /// entry — a UI would then render "denied by: (nothing)". The empty-entry filter is what keeps
    /// "allowed" and "denied for an unnamed reason" distinguishable.
    /// </remarks>
    private static RiskDecisionDto Project(RiskDecision risk) => new(
        risk.Id,
        risk.Allowed,
        risk.FailedChecksCsv
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries),
        risk.Detail,
        risk.SnapshotJson,
        risk.EvaluatedAt);

    private static ExchangeOrderDto Project(ExchangeOrder order, IReadOnlyList<OrderFill> allFills) => new(
        order.Id,
        order.Venue,
        order.VenueOrderId,
        order.ClientOrderId,
        order.Status,
        order.FilledQuantity,
        order.AverageFillPrice,
        order.RequestHash,
        order.ResponseHash,
        order.SubmittedAt,
        order.VenueUpdatedAt,
        order.LastReconciledAt,
        allFills
            .Where(fill => fill.ExchangeOrderId == order.Id)
            .Select(Project)
            .ToList());

    private static OrderFillDto Project(OrderFill fill) => new(
        fill.Id,
        fill.Venue,
        fill.VenueTradeId,
        fill.Price,
        fill.Quantity,
        fill.Fee,
        fill.FeeAsset,
        fill.IsMaker,
        fill.ExecutedAt);

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

    private static BotAuditEventDto Project(BotAuditEvent auditEvent) => new(
        auditEvent.Id,
        auditEvent.BotId,
        auditEvent.OperatingMode,
        auditEvent.EventType,
        auditEvent.CorrelationId,
        auditEvent.Sequence,
        auditEvent.Summary,
        auditEvent.DetailJson,
        auditEvent.Symbol,
        auditEvent.CandleOpenTime,
        auditEvent.ModelVersion,
        auditEvent.StrategyDecisionId,
        auditEvent.OrderIntentId,
        auditEvent.RiskDecisionId,
        auditEvent.ExchangeOrderId,
        auditEvent.OrderFillId,
        auditEvent.BotPositionId,
        auditEvent.KillSwitchId,
        auditEvent.ActorUserName,
        auditEvent.OccurredAt);

    #endregion
}
