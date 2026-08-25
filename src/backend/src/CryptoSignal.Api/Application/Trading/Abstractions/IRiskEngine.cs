using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;

namespace CryptoSignal.Api.Application.Trading.Abstractions;

/// <summary>
/// The single gate between an intent and a venue. Nothing reaches a broker without passing here.
/// </summary>
/// <remarks>
/// <para>
/// Every check runs against one snapshot taken at the start of the evaluation, and no check re-reads
/// the database. Two checks disagreeing because a balance moved between them is not a hypothetical —
/// it is how a limit gets passed twice by the same order — so the snapshot is frozen and the checks are
/// pure functions of it.
/// </para>
/// <para>
/// The outcome space is allow or deny, with no "allow with a warning". A check that cannot be completed
/// denies.
/// </para>
/// </remarks>
public interface IRiskEngine
{
    Task<RiskVerdict> EvaluateAsync(RiskEvaluationContext context, CancellationToken cancellationToken);
}

/// <summary>
/// Everything the caller already holds when it asks for a verdict. The engine reads the rest itself so
/// the snapshot is taken in one place, at one moment.
/// </summary>
/// <param name="Bot">The bot, with its own limits — the tighter of bot and platform limit always wins.</param>
/// <param name="Decision">The persisted decision this intent realises. Its provenance is checked, not trusted.</param>
/// <param name="Intent">The intent under evaluation, already constructed but not yet submitted.</param>
/// <param name="Rules">The venue's filters for the symbol.</param>
/// <param name="NewestCandleOpenTime">Open time of the newest closed candle the decision saw.</param>
/// <param name="AvailableQuoteBalance">
/// Free quote balance as the broker reports it, already net of what open orders reserve. Null means the
/// balance could not be read, which denies — an unknown balance is not a sufficient one.
/// </param>
public sealed record RiskEvaluationContext(
    TradingBot Bot,
    StrategyDecision Decision,
    OrderIntent Intent,
    InstrumentRules Rules,
    DateTime NewestCandleOpenTime,
    decimal? AvailableQuoteBalance);

/// <summary>
/// The verdict, and the evidence behind it. Persisted as a <see cref="RiskDecision"/> whether it allowed
/// or denied — a refusal is evidence, not an error to be discarded.
/// </summary>
/// <param name="Allowed">True only when every check passed.</param>
/// <param name="FailedChecks">The checks that failed, in enum order. Empty when allowed.</param>
/// <param name="Detail">Human-readable reasons, one per failed check.</param>
/// <param name="SnapshotJson">The snapshot the checks ran against, so a post-mortem sees what they saw.</param>
public sealed record RiskVerdict(
    bool Allowed,
    IReadOnlyList<RiskCheck> FailedChecks,
    string? Detail,
    string SnapshotJson)
{
    /// <summary>The failed checks as the CSV the <see cref="RiskDecision"/> column stores.</summary>
    public string FailedChecksCsv => string.Join(',', FailedChecks.Select(c => c.ToString()));
}
