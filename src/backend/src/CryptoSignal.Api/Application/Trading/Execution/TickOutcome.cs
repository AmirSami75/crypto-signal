using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Execution;

/// <summary>What one bot tick concluded. Every terminal state is named, including the ones that traded nothing.</summary>
public enum TickResult
{
    /// <summary>The lock was held by another worker. Not this worker's turn; try next cycle.</summary>
    Skipped = 1,

    /// <summary>A kill switch in scope blocked the tick before any work was done.</summary>
    Blocked = 2,

    /// <summary>Already decided on this candle. The idempotency guarantee doing its job — a no-op.</summary>
    AlreadyEvaluated = 3,

    /// <summary>The engine advised HOLD. A decision was recorded; no order was placed.</summary>
    Hold = 4,

    /// <summary>The risk engine denied the intent. Recorded as a denial; no order was placed.</summary>
    RiskDenied = 5,

    /// <summary>An order was placed and its result recorded.</summary>
    Traded = 6,

    /// <summary>
    /// The bot faulted on something it must not trade through — a missing candle window, an ambiguous
    /// order outcome. It is halted and needs an operator.
    /// </summary>
    Faulted = 7,
}

/// <summary>The result of a tick, with enough context for the scheduler to log and update counters.</summary>
public sealed record TickOutcome(
    TickResult Result,
    string CorrelationId,
    Guid? StrategyDecisionId = null,
    Guid? OrderIntentId = null,
    BotDecisionAction? Action = null,
    IReadOnlyList<RiskCheck>? FailedChecks = null,
    string? Message = null)
{
    public bool PlacedOrder => Result == TickResult.Traded;
    public bool RecordedDecision => StrategyDecisionId is not null;
}
