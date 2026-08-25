using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Abstractions;

/// <summary>
/// Appends links to the causal chain the safety policy requires: candle → model version → signal →
/// decision → intent → risk decision → approval → exchange request/response → order events → fills →
/// position → reconciliation.
/// </summary>
/// <remarks>
/// <para>
/// The chain records refusals as carefully as fills. "Why did the platform not place this trade" is the
/// first question an incident review asks, and a chain holding only the successful path cannot answer it.
/// </para>
/// <para>
/// Appending never aborts the operation it describes. The authoritative records live in their own tables
/// behind their own constraints — the chain is a queryable index over them, not the only copy — so
/// failing a tick because its audit row could not be written would turn an observability fault into an
/// execution fault. A failed append is logged at error level instead.
/// </para>
/// </remarks>
public interface IBotAuditTrail
{
    /// <summary>Appends one event, assigning it the next sequence number within its correlation.</summary>
    Task AppendAsync(BotAuditEntry entry, CancellationToken cancellationToken);
}

/// <summary>
/// One event to append. <paramref name="Detail"/> is serialised to the row's <c>jsonb</c> column.
/// </summary>
/// <remarks>
/// <b>Nothing secret goes in <paramref name="Detail"/>.</b> Not an API key, not a signed query string,
/// not a request header, not a raw venue payload — the audit table is read by operators and exported to
/// dashboards. Exchange requests and responses are recorded as hashes on <c>ExchangeOrders</c> for
/// exactly this reason.
/// </remarks>
public sealed record BotAuditEntry(
    string CorrelationId,
    BotAuditEventType EventType,
    OperatingMode OperatingMode,
    string Summary,
    Guid? BotId = null,
    object? Detail = null,
    Guid? StrategyDecisionId = null,
    Guid? OrderIntentId = null,
    Guid? RiskDecisionId = null,
    Guid? ExchangeOrderId = null,
    Guid? OrderFillId = null,
    Guid? BotPositionId = null,
    Guid? KillSwitchId = null,
    string? Symbol = null,
    DateTime? CandleOpenTime = null,
    string? ModelVersion = null,
    Guid? ActorUserId = null,
    string? ActorUserName = null);
