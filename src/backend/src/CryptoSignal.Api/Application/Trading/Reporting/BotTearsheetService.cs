using CryptoSignal.Api.Application.DTOs.Trading;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.Application.Trading.Reporting;

/// <summary>
/// Read-only tearsheet reporting for one bot. Never writes, never places orders, never touches risk.
/// </summary>
/// <remarks>
/// Queries the existing tables only (<c>StrategyDecision</c>, <c>BotPosition</c>, <c>OrderFill</c>) with
/// no-tracking reads, then delegates every number to <see cref="BotTearsheetCalculator"/> — a pure
/// function over in-memory lists, which is what the unit tests exercise.
/// </remarks>
public sealed class BotTearsheetService(
    IRepo<StrategyDecision> decisions,
    IRepo<BotPosition> positions,
    IRepo<OrderFill> fills) : IScopedSvcMarker
{
    public async Task<BotTearsheetDto> GetAsync(Guid botId, int days, DateTime utcNow, CancellationToken ct)
    {
        days = Math.Clamp(days, 1, 365);
        var to = utcNow;
        var from = to.AddDays(-days);

        var decisionRows = await decisions.TableNoTracking
            .Where(row => row.BotId == botId && row.CreatedAt >= from)
            .ToListAsync(ct);

        var closedPositions = await positions.TableNoTracking
            .Where(row => row.BotId == botId
                && row.Status == PositionStatus.Closed
                && (row.ClosedAt ?? row.OpenedAt) >= from)
            .ToListAsync(ct);

        var fillsIncluded = await fills.TableNoTracking
            .Where(row => row.BotId == botId && row.ExecutedAt >= from)
            .AnyAsync(ct);

        return BotTearsheetCalculator.Build(botId, days, from, to, decisionRows, closedPositions, fillsIncluded);
    }
}

/// <summary>
/// Pure tearsheet math over in-memory rows. Clean-room implementation: no third-party statistics
/// dependency, every metric defined in the remarks of <see cref="Build"/>.
/// </summary>
public static class BotTearsheetCalculator
{
    public const int HistogramBins = 10;

    /// <summary>
    /// Builds the tearsheet.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <c>decisions</c> counts every <see cref="StrategyDecision"/> in the window (HOLDs included — a
    /// quiet tick is evidence the bot was alive and declining, not absence of data);
    /// <c>entries</c> counts <c>Action == Open</c> only.
    /// </para>
    /// <para>
    /// The trade series is the closed positions' <c>RealizedPnl</c> in close order when any exist,
    /// else the entry decisions' <c>ExpectedValue</c> (ATR units) as a proxy. From that series:
    /// win rate is wins / trades; expectancy is the mean; profit factor is gross wins over gross
    /// losses; Sharpe is the per-trade mean over sample standard deviation (not annualised);
    /// max drawdown is the worst peak-to-trough decline of the cumulative curve (a non-negative
    /// magnitude); ROMAD is total return over max drawdown.
    /// </para>
    /// </remarks>
    public static BotTearsheetDto Build(
        Guid botId,
        int days,
        DateTime from,
        DateTime to,
        IReadOnlyList<StrategyDecision> decisions,
        IReadOnlyList<BotPosition> closedPositions,
        bool fillsIncluded)
    {
        var entries = decisions.Count(row => row.Action == BotDecisionAction.Open);

        var reasonBreakdown = decisions
            .GroupBy(row => string.IsNullOrWhiteSpace(row.ReasonCode) ? "unknown" : row.ReasonCode)
            .ToDictionary(group => group.Key, group => group.Count());

        var histogram = new int[HistogramBins];
        foreach (var row in decisions)
        {
            var confidence = Math.Clamp(row.Confidence, 0.0, 1.0);
            var bin = Math.Min(HistogramBins - 1, (int)(confidence * HistogramBins));
            histogram[bin]++;
        }

        IReadOnlyList<double> series = closedPositions.Count > 0
            ? closedPositions
                .OrderBy(position => position.ClosedAt ?? position.OpenedAt)
                .Select(position => (double)position.RealizedPnl)
                .ToList()
            : decisions
                .Where(row => row.Action == BotDecisionAction.Open)
                .Select(row => row.ExpectedValue)
                .ToList();

        double? winRate = null;
        double? expectancy = null;
        double? profitFactor = null;
        double? sharpe = null;
        double? maxDrawdown = null;
        double? romad = null;

        if (series.Count > 0)
        {
            var wins = series.Count(value => value > 0);
            winRate = (double)wins / series.Count;
            expectancy = series.Average();

            var grossWin = series.Where(value => value > 0).Sum();
            var grossLoss = -series.Where(value => value < 0).Sum();
            profitFactor = grossLoss > 0 ? grossWin / grossLoss : null;

            if (series.Count >= 2)
            {
                var mean = expectancy.Value;
                var variance = series.Sum(value => (value - mean) * (value - mean)) / (series.Count - 1);
                sharpe = variance > 0 ? mean / Math.Sqrt(variance) : null;
            }

            var peak = 0.0;
            var equity = 0.0;
            var worst = 0.0;
            foreach (var value in series)
            {
                equity += value;
                peak = Math.Max(peak, equity);
                worst = Math.Max(worst, peak - equity);
            }

            maxDrawdown = worst;
            var total = equity;
            romad = worst > 0 ? total / worst : null;
        }

        return new BotTearsheetDto(
            botId,
            new BotTearsheetPeriodDto(days, from, to),
            decisions.Count,
            entries,
            fillsIncluded,
            winRate,
            expectancy,
            profitFactor,
            sharpe,
            maxDrawdown,
            romad,
            reasonBreakdown,
            histogram);
    }
}
