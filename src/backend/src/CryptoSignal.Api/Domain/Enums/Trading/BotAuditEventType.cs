using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// One link in the causal chain the safety policy requires:
/// candle → model version → signal → strategy decision → order intent → risk decision → approval →
/// exchange request/response → order events → fills → balance/position → reconciliation.
/// </summary>
/// <remarks>
/// Every member names something that actually happened, including the refusals. A chain that records
/// only the successful path cannot answer the question an incident review asks first, which is why a
/// trade the platform declined to place did not get placed.
/// </remarks>
public enum BotAuditEventType
{
    /// <summary>The candle window a decision was computed from was recorded.</summary>
    [Display(Name = "Candle window recorded")] CandleWindowRecorded = 1,

    /// <summary>The engine was asked for a decision.</summary>
    [Display(Name = "Engine consulted")] EngineConsulted = 2,

    /// <summary>The engine answered, and the answer was persisted as a strategy decision.</summary>
    [Display(Name = "Strategy decision recorded")] StrategyDecisionRecorded = 3,

    /// <summary>An order intent was constructed from a decision.</summary>
    [Display(Name = "Order intent created")] OrderIntentCreated = 4,

    /// <summary>The risk engine allowed the intent.</summary>
    [Display(Name = "Risk allowed")] RiskAllowed = 5,

    /// <summary>The risk engine denied the intent, naming the checks that failed.</summary>
    [Display(Name = "Risk denied")] RiskDenied = 6,

    /// <summary>An operator approved the intent.</summary>
    [Display(Name = "Approval granted")] ApprovalGranted = 7,

    /// <summary>The intent was submitted to a venue.</summary>
    [Display(Name = "Order submitted")] OrderSubmitted = 8,

    /// <summary>The venue reported a state change.</summary>
    [Display(Name = "Order state changed")] OrderStateChanged = 9,

    /// <summary>A fill was recorded.</summary>
    [Display(Name = "Fill recorded")] FillRecorded = 10,

    /// <summary>A position was opened, adjusted or closed.</summary>
    [Display(Name = "Position changed")] PositionChanged = 11,

    /// <summary>Platform state was compared against the venue's.</summary>
    [Display(Name = "Reconciled")] Reconciled = 12,

    /// <summary>A kill switch in scope blocked the tick.</summary>
    [Display(Name = "Kill switch blocked")] KillSwitchBlocked = 13,

    /// <summary>The bot faulted and stopped trading.</summary>
    [Display(Name = "Bot faulted")] BotFaulted = 14,

    /// <summary>An operator changed the bot's status or configuration.</summary>
    [Display(Name = "Configuration changed")] ConfigurationChanged = 15,
}
