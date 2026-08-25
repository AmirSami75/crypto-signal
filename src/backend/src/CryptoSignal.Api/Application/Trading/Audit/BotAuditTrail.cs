using System.Collections.Concurrent;
using System.Text.Json;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;

namespace CryptoSignal.Api.Application.Trading.Audit;

/// <summary>
/// Writes audit events with a monotonic sequence per correlation id.
/// </summary>
/// <remarks>
/// <para>
/// Scoped, and one scope is one tick — which is what makes the in-memory sequence counter correct. The
/// unique index on <c>(CorrelationId, Sequence)</c> is the backstop: if two scopes ever shared a
/// correlation id, the second write would be rejected rather than silently interleaved into a chain
/// whose order no longer means anything.
/// </para>
/// <para>
/// Summaries are truncated to the column width rather than left to fail at the database. An audit row
/// lost to a length violation is the one row an incident review most wants.
/// </para>
/// </remarks>
public sealed class BotAuditTrail(
    IRepo<BotAuditEvent> events,
    ILogger<BotAuditTrail> logger) : IBotAuditTrail, IScopedSvcMarker
{
    private const int SummaryMaxLength = 500;

    private static readonly JsonSerializerOptions DetailJson = new()
    {
        WriteIndented = false,
        MaxDepth = 8,
    };

    private readonly ConcurrentDictionary<string, int> _sequences = new();

    public async Task AppendAsync(BotAuditEntry entry, CancellationToken cancellationToken)
    {
        try
        {
            var sequence = _sequences.AddOrUpdate(entry.CorrelationId, 1, (_, current) => current + 1);

            var row = new BotAuditEvent
            {
                BotId = entry.BotId,
                OperatingMode = entry.OperatingMode,
                EventType = entry.EventType,
                OccurredAt = DateTime.UtcNow,
                CorrelationId = entry.CorrelationId,
                Sequence = sequence,
                Summary = Truncate(entry.Summary, SummaryMaxLength),
                DetailJson = Serialize(entry.Detail),
                StrategyDecisionId = entry.StrategyDecisionId,
                OrderIntentId = entry.OrderIntentId,
                RiskDecisionId = entry.RiskDecisionId,
                ExchangeOrderId = entry.ExchangeOrderId,
                OrderFillId = entry.OrderFillId,
                BotPositionId = entry.BotPositionId,
                KillSwitchId = entry.KillSwitchId,
                Symbol = entry.Symbol,
                CandleOpenTime = entry.CandleOpenTime,
                ModelVersion = entry.ModelVersion,
                ActorUserId = entry.ActorUserId,
                ActorUserName = entry.ActorUserName,
            };

            await events.AddAsync(row, saveNow: true, cancellationToken);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            // Deliberately swallowed. See IBotAuditTrail: the operation being described has already
            // happened, and failing it now would not un-place an order — it would only hide the failure.
            logger.LogError(
                exception,
                "Audit append failed for {EventType} on bot {BotId} (correlation {CorrelationId})",
                entry.EventType,
                entry.BotId,
                entry.CorrelationId);
        }
    }

    private string? Serialize(object? detail)
    {
        if (detail is null)
            return null;

        try
        {
            return JsonSerializer.Serialize(detail, DetailJson);
        }
        catch (Exception exception)
        {
            logger.LogWarning(exception, "Audit detail could not be serialised; storing the failure instead");
            return $"{{\"serializationError\":\"{exception.GetType().Name}\"}}";
        }
    }

    private static string Truncate(string value, int max) =>
        string.IsNullOrEmpty(value) || value.Length <= max ? value : value[..max];
}
