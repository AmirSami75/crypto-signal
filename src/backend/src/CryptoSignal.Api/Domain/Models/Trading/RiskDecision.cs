using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// The immutable verdict of the risk engine on one <see cref="OrderIntent"/>: allow, or deny with the
/// exact set of checks that failed. Bound one-to-one to the intent.
/// </summary>
/// <remarks>
/// <para>
/// The engine evaluates every check against one consistent snapshot and records the inputs it read, so
/// this row answers not just "was it allowed" but "on what basis" — the balance, exposure, limits and
/// switch states as they stood at the instant of the decision. A denial that cannot name its failed
/// checks is not a denial this platform can audit, which is why <see cref="FailedChecksCsv"/> is
/// populated from the typed <c>RiskCheck</c> enum rather than free prose.
/// </para>
/// <para>
/// Risk decisions are immutable. If the intent they judged changes in any material way it needs a new
/// intent and a new decision — this row is never edited to reflect a later state.
/// </para>
/// </remarks>
public class RiskDecision : BaseEntity
{
    /// <summary>The intent judged. Unique — one risk decision per intent.</summary>
    public Guid OrderIntentId { get; set; }

    /// <summary>The bot, copied for direct querying.</summary>
    public Guid BotId { get; set; }

    /// <summary>Whether the order may proceed. False whenever any required check failed or could not complete.</summary>
    public bool Allowed { get; set; }

    /// <summary>
    /// The failed <c>RiskCheck</c> members, comma-separated by member name. Empty when allowed. Stored
    /// as names rather than numbers so the row stays legible in a database console during an incident.
    /// </summary>
    public string FailedChecksCsv { get; set; } = string.Empty;

    /// <summary>Human-readable summary of the denial, assembled from the failed checks.</summary>
    public string? Detail { get; set; }

    /// <summary>
    /// JSON of the snapshot the checks read — balances, exposure, limits, switch states. Diagnostic
    /// only, and it carries no credentials or headers.
    /// </summary>
    public string? SnapshotJson { get; set; }

    /// <summary>When the decision was made.</summary>
    public DateTime EvaluatedAt { get; set; }
}
