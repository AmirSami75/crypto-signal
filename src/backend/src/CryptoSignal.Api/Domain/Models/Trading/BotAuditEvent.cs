using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// One append-only link in the causal chain from candle to final account state. Rows are written, never
/// updated, and the foreign keys are deliberately loose <see cref="Guid"/>? columns so an event about a
/// stage can be recorded even when a later stage never happened.
/// </summary>
/// <remarks>
/// <para>
/// The chain the safety policy requires is: candle → model version → signal → strategy decision → order
/// intent → risk decision → approval → exchange request/response → order events → fills →
/// balance/position → reconciliation. <see cref="CorrelationId"/> threads one tick's events together and
/// <see cref="Sequence"/> orders them within it, because timestamps at millisecond resolution tie.
/// </para>
/// <para>
/// The refusals are recorded as carefully as the successes. An incident review's first question is
/// usually why something did <i>not</i> happen, and a chain that logs only completed orders cannot
/// answer it.
/// </para>
/// </remarks>
public class BotAuditEvent : BaseEntity
{
    /// <summary>The bot concerned, or null for a platform-scoped event such as a global kill switch.</summary>
    public Guid? BotId { get; set; }

    /// <summary>Which venue class the event belongs to. Filtered on every read.</summary>
    public OperatingMode OperatingMode { get; set; }

    /// <summary>Which link in the chain this is.</summary>
    public BotAuditEventType EventType { get; set; }

    /// <summary>When it happened.</summary>
    public DateTime OccurredAt { get; set; }

    /// <summary>Ties one tick's events together. Carries no credentials.</summary>
    public string CorrelationId { get; set; } = string.Empty;

    /// <summary>Orders events within a correlation, since equal timestamps do not.</summary>
    public int Sequence { get; set; }

    /// <summary>One-line description. The column an operator scans.</summary>
    public string Summary { get; set; } = string.Empty;

    /// <summary>Structured detail as JSON. Never credentials, tokens or headers.</summary>
    public string? DetailJson { get; set; }

    #region Chain references

    public Guid? StrategyDecisionId { get; set; }
    public Guid? OrderIntentId { get; set; }
    public Guid? RiskDecisionId { get; set; }
    public Guid? ExchangeOrderId { get; set; }
    public Guid? OrderFillId { get; set; }
    public Guid? BotPositionId { get; set; }
    public Guid? KillSwitchId { get; set; }

    /// <summary>Symbol, when the event is about one.</summary>
    public string? Symbol { get; set; }

    /// <summary>Candle the event traces back to, when it traces to one.</summary>
    public DateTime? CandleOpenTime { get; set; }

    /// <summary>Model version in force, when the event involves the engine.</summary>
    public string? ModelVersion { get; set; }

    #endregion

    #region Actor

    /// <summary>The operator who caused the event, for operator-initiated ones.</summary>
    public Guid? ActorUserId { get; set; }

    public string? ActorUserName { get; set; }

    #endregion
}
