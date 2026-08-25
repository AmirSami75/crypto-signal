using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// One stretch of a bot being scheduled, with the lease that keeps exactly one worker on it and the
/// counters that describe what it did.
/// </summary>
/// <remarks>
/// The lease exists because two API replicas evaluating one bot would double-trade it. The scheduler
/// takes a Postgres advisory lock on the bot id for the duration of a tick — that is the real mutual
/// exclusion — and this row is the durable, queryable record of who holds the bot and when it last
/// proved it was alive. A heartbeat that stops advancing is how a wedged worker becomes visible.
/// </remarks>
public class BotRun : BaseEntity
{
    /// <summary>The bot being run.</summary>
    public Guid BotId { get; set; }

    /// <summary>Copied from the bot so a run can be read without joining, and filtered by mode.</summary>
    public OperatingMode OperatingMode { get; set; }

    /// <summary>Identifies the worker holding the lease — host and process, not a person.</summary>
    public string LeaseOwner { get; set; } = string.Empty;

    /// <summary>When this run started.</summary>
    public DateTime StartedAt { get; set; }

    /// <summary>Last time the worker proved it was alive.</summary>
    public DateTime LastHeartbeatAt { get; set; }

    /// <summary>When the run ended, or null while it is current.</summary>
    public DateTime? EndedAt { get; set; }

    /// <summary>Ticks attempted.</summary>
    public long TickCount { get; set; }

    /// <summary>Strategy decisions persisted.</summary>
    public long DecisionCount { get; set; }

    /// <summary>Order intents that reached a venue.</summary>
    public long OrderCount { get; set; }

    /// <summary>Ticks that raised.</summary>
    public long ErrorCount { get; set; }

    /// <summary>Consecutive failures, reset by a clean tick. Feeds the bot's failure limit.</summary>
    public int ConsecutiveFailureCount { get; set; }

    /// <summary>Most recent error message. Never carries credentials or headers.</summary>
    public string? LastError { get; set; }

    /// <summary>When the most recent error occurred.</summary>
    public DateTime? LastErrorAt { get; set; }

    /// <summary>When the most recent tick completed.</summary>
    public DateTime? LastTickAt { get; set; }
}
