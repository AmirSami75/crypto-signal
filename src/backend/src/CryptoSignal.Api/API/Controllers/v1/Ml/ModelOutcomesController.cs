using Microsoft.EntityFrameworkCore;
using CryptoSignal.Api.Adapter.Persistence.Contexts;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using Microsoft.AspNetCore.Mvc;

namespace CryptoSignal.Api.API.Controllers.v1.Ml;

/// <summary>One closed position joined to the decision that opened it: what the model bet, what happened.</summary>
public sealed record DecisionOutcomeDto(
    Guid DecisionId,
    Guid PositionId,
    string Symbol,
    string Interval,
    DateTime CandleOpenTime,
    TradeDirection PredictedDirection,
    double Confidence,
    double ExpectedValue,
    string ModelVersion,
    bool UsedWildcardModel,
    decimal RealizedPnl,
    int BarsHeld,
    PositionCloseReason CloseReason,
    DateTime ClosedAt);

/// <summary>Aggregates over the outcomes: how well did predicted confidence track realized results.</summary>
public sealed record OutcomeReportDto
{
    /// <summary>Closed trades with a linked decision — the sample behind every number here.</summary>
    public int SampleSize { get; init; }

    public int Wins { get; init; }
    public int Losses { get; init; }
    public decimal TotalRealizedPnl { get; init; }

    /// <summary>Average realized P&amp;L per trade, in quote currency.</summary>
    public decimal AverageRealizedPnl { get; init; }

    /// <summary>
    /// Confidence buckets with observed win rates. A calibrated model shows bucket win rates rising
    /// in step with their centers; flat or inverted rows are the earliest visible sign of drift.
    /// </summary>
    public IReadOnlyList<ConfidenceBucketDto> CalibrationBuckets { get; init; } = [];

    public IReadOnlyList<SymbolOutcomeDto> PerSymbol { get; init; } = [];
}

public sealed record ConfidenceBucketDto(double Lower, double Upper, int Trades, int Wins, decimal TotalPnl);

public sealed record SymbolOutcomeDto(string Symbol, int Trades, int Wins, decimal TotalPnl);

// Buckets are fixed at report time rather than configured: five equally-sized bands cover the whole
// [0,1) range and match how the promotion gate will read calibration. Changing the grid would make
// historical reports incomparable, so it is deliberately hard-coded.
internal static class ConfidenceBuckets
{
    public static readonly (double Lower, double Upper)[] Bands =
    [
        (0.50, 0.60),
        (0.60, 0.70),
        (0.70, 0.80),
        (0.80, 0.90),
        (0.90, 1.01), // upper bound inclusive so confidence 1.00 lands somewhere
    ];
}

/// <summary>
/// The self-learning loop's read side: joins closed positions back to the decisions that opened
/// them and reports prediction-versus-actual.
/// </summary>
/// <remarks>
/// <para>
/// No new table. Every fact this reports already exists — <c>BotPositions</c> carries the outcome,
/// the intent chain carries the decision id, <c>StrategyDecisions</c> carries the prediction. The
/// loop's capture step is a join, not a write: a second copy of the truth would only drift from it.
/// </para>
/// <para>
/// A win is any closed trade with positive realized P&amp;L regardless of which barrier touched
/// first — the model bets on expected value net of costs, and that is what the outcome measures.
/// </para>
/// </remarks>
[CustomAuthorize]
[ControllerInfo("ModelOutcomes", "ارزیابی مدل بر اساس نتایج")]
public class ModelOutcomesController(
    CryptoSignalDbContext db) : BaseController
{
    [HttpGet("bot/{botId:guid}/outcomes")]
    [Permission(PermissionType.Custom, nameof(GetForBot), "گزارش پیش‌بینی در برابر نتیجه برای یک ربات")]
    public async Task<ApiResult<OutcomeReportDto>> GetForBot(Guid botId, CancellationToken ct)
    {
        var rows = await QueryAsync(x => x.BotId == botId, ct);
        return Build(rows);
    }

    [HttpGet("outcomes")]
    [Permission(PermissionType.Get)]
    public async Task<ApiResult<OutcomeReportDto>> GetAll(CancellationToken ct)
    {
        var rows = await QueryAsync(_ => true, ct);
        return Build(rows);
    }

    // The join projects into an anonymous type inside SQL and maps to the record after
    // materialization — constructing a positional record inside the query tree is what EF cannot
    // translate here.
    private async Task<List<DecisionOutcomeRow>> QueryAsync(
        System.Linq.Expressions.Expression<Func<BotPosition, bool>> predicate, CancellationToken ct) =>
        (
            await db.Set<BotPosition>().AsNoTracking()
                .Where(predicate)
                .Where(p => p.Status == PositionStatus.Closed && p.ClosedByOrderIntentId != null)
                .Join(db.Set<OrderIntent>().AsNoTracking().Select(i => new { i.Id }),
                    p => p.ClosedByOrderIntentId,
                    i => i.Id,
                    (p, _) => new { Position = p })
                .Join(db.Set<OrderIntent>().AsNoTracking().Select(i => new { i.Id, i.StrategyDecisionId }),
                    x => x.Position.OpenedByOrderIntentId,
                    i => i.Id,
                    (x, openIntent) => new { x.Position, openIntent.StrategyDecisionId })
                .Join(db.Set<StrategyDecision>().AsNoTracking(),
                    x => x.StrategyDecisionId,
                    d => d.Id,
                    (x, d) => new
                    {
                        PositionId = x.Position.Id,
                        DecisionId = d.Id,
                        x.Position.Symbol,
                        x.Position.RealizedPnl,
                        x.Position.BarsHeld,
                        CloseReason = x.Position.CloseReason!.Value,
                        ClosedAt = x.Position.ClosedAt!.Value,
                        d.Direction,
                        d.Confidence,
                        d.ExpectedValue,
                        d.ModelVersion,
                        d.UsedWildcardModel,
                    })
                .OrderByDescending(r => r.ClosedAt)
                .ToListAsync(ct)
        )
        .Select(r => new DecisionOutcomeRow(
            r.PositionId, r.DecisionId, r.Symbol, r.RealizedPnl, r.BarsHeld,
            r.CloseReason, r.ClosedAt, r.Direction, r.Confidence,
            r.ExpectedValue, r.ModelVersion, r.UsedWildcardModel))
        .ToList();

    private static ApiResult<OutcomeReportDto> Build(List<DecisionOutcomeRow> rows)
    {
        var wins = rows.Count(r => r.RealizedPnl > 0);
        var totalPnl = rows.Sum(r => r.RealizedPnl);

        var buckets = ConfidenceBuckets.Bands
            .Select(band =>
            {
                var inBand = rows.Where(r => r.Confidence >= band.Lower && r.Confidence < band.Upper).ToList();
                return new ConfidenceBucketDto(
                    band.Lower, Math.Min(band.Upper, 1.0),
                    inBand.Count,
                    inBand.Count(r => r.RealizedPnl > 0),
                    inBand.Sum(r => r.RealizedPnl));
            })
            .ToList();

        var perSymbol = rows
            .GroupBy(r => r.Symbol)
            .Select(g => new SymbolOutcomeDto(
                g.Key, g.Count(), g.Count(r => r.RealizedPnl > 0), g.Sum(r => r.RealizedPnl)))
            .ToList();

        return new OutcomeReportDto
        {
            SampleSize = rows.Count,
            Wins = wins,
            Losses = rows.Count - wins,
            TotalRealizedPnl = totalPnl,
            AverageRealizedPnl = rows.Count == 0 ? 0 : decimal.Round(totalPnl / rows.Count, 10),
            CalibrationBuckets = buckets,
            PerSymbol = perSymbol,
        };
    }

    /// <summary>Projection of the join, kept as a record so EF can materialize it without tracking.</summary>
    private sealed record DecisionOutcomeRow(
        Guid PositionId,
        Guid DecisionId,
        string Symbol,
        decimal RealizedPnl,
        int BarsHeld,
        PositionCloseReason CloseReason,
        DateTime ClosedAt,
        TradeDirection PredictedDirection,
        double Confidence,
        double ExpectedValue,
        string ModelVersion,
        bool UsedWildcardModel);
}
