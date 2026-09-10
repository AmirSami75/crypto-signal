using CryptoSignal.Api.Application.DTOs.Trading;
using CryptoSignal.Api.Application.Trading.Reporting;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using Xunit;

namespace CryptoSignal.Tests;

/// <summary>
/// Tearsheet math over in-memory rows: the pure <see cref="BotTearsheetCalculator"/> the
/// <c>GET /api/v1/bot/{id}/tearsheet</c> endpoint is built on. No database, no web host —
/// lists in, numbers out.
/// </summary>
public sealed class BotTearsheetTests
{
    private static readonly DateTime To = new(2026, 9, 10, 0, 0, 0, DateTimeKind.Utc);
    private static readonly DateTime From = To.AddDays(-30);

    private static StrategyDecision Decision(
        BotDecisionAction action = BotDecisionAction.Open,
        string reason = "entry",
        double confidence = 0.6,
        double expectedValue = 0.5) => new()
    {
        BotId = Guid.CreateVersion7(),
        Symbol = "BTCUSDT",
        Interval = "1h",
        CandleOpenTime = From.AddDays(1),
        CandleWindowDigest = "digest",
        Action = action,
        Direction = TradeDirection.Long,
        ReasonCode = reason,
        Confidence = confidence,
        ExpectedValue = expectedValue,
        ModelId = "m",
        ModelVersion = "1",
    };

    private static BotPosition ClosedPosition(decimal realizedPnl, int dayOffset) => new()
    {
        BotId = Guid.CreateVersion7(),
        Symbol = "BTCUSDT",
        Direction = TradeDirection.Long,
        Status = PositionStatus.Closed,
        OpenedAt = From.AddDays(dayOffset),
        ClosedAt = From.AddDays(dayOffset).AddHours(1),
        RealizedPnl = realizedPnl,
    };

    private static BotTearsheetDto Build(
        IReadOnlyList<StrategyDecision>? decisions = null,
        IReadOnlyList<BotPosition>? positions = null,
        bool fillsIncluded = false) =>
        BotTearsheetCalculator.Build(
            Guid.CreateVersion7(), 30, From, To,
            decisions ?? [], positions ?? [], fillsIncluded);

    [Fact]
    public void Response_carries_the_required_shape()
    {
        var sheet = Build();

        Assert.Equal(30, sheet.Period.Days);
        Assert.Equal(0, sheet.Decisions);
        Assert.Equal(0, sheet.Entries);
        Assert.False(sheet.FillsIncluded);
        Assert.Null(sheet.WinRate);
        Assert.Null(sheet.ExpectancyAtr);
        Assert.Null(sheet.ProfitFactor);
        Assert.Null(sheet.Sharpe);
        Assert.Null(sheet.MaxDrawdown);
        Assert.Null(sheet.Romad);
        Assert.Empty(sheet.ReasonBreakdown);
        Assert.Equal(Enumerable.Repeat(0, 10).ToList(), sheet.ConfidenceHistogram.ToList());
    }

    [Fact]
    public void Holds_count_as_decisions_but_not_entries()
    {
        var sheet = Build(decisions:
        [
            Decision(BotDecisionAction.Hold),
            Decision(BotDecisionAction.Open),
            Decision(BotDecisionAction.Close),
        ]);

        Assert.Equal(3, sheet.Decisions);
        Assert.Equal(1, sheet.Entries);
    }

    [Fact]
    public void Decisions_only_falls_back_to_expected_value_proxy()
    {
        // Series [1.0, -0.5, 0.5]: equity 1.0 -> 0.5 -> 1.0, worst drawdown 0.5, total 1.0.
        var sheet = Build(
            decisions:
            [
                Decision(expectedValue: 1.0),
                Decision(expectedValue: -0.5),
                Decision(expectedValue: 0.5),
            ],
            fillsIncluded: false);

        Assert.False(sheet.FillsIncluded);
        Assert.Equal(3, sheet.Decisions);
        Assert.Equal(3, sheet.Entries);
        Assert.Equal(2.0 / 3.0, sheet.WinRate!.Value, precision: 10);
        Assert.Equal(1.0 / 3.0, sheet.ExpectancyAtr!.Value, precision: 10);
        Assert.Equal(3.0, sheet.ProfitFactor!.Value, precision: 10);
        Assert.Equal(0.5, sheet.MaxDrawdown!.Value, precision: 10);
        Assert.Equal(2.0, sheet.Romad!.Value, precision: 10);
        Assert.NotNull(sheet.Sharpe);
    }

    [Fact]
    public void Closed_positions_drive_trade_metrics_when_fills_included()
    {
        var sheet = Build(
            decisions: [Decision(), Decision()],
            positions:
            [
                ClosedPosition(100m, dayOffset: 1),
                ClosedPosition(-50m, dayOffset: 2),
                ClosedPosition(-25m, dayOffset: 3),
            ],
            fillsIncluded: true);

        Assert.True(sheet.FillsIncluded);
        Assert.Equal(2, sheet.Decisions);
        Assert.Equal(2, sheet.Entries);
        Assert.Equal(1.0 / 3.0, sheet.WinRate!.Value, precision: 10);
        Assert.Equal(25.0 / 3.0, sheet.ExpectancyAtr!.Value, precision: 10);
        Assert.Equal(100.0 / 75.0, sheet.ProfitFactor!.Value, precision: 10);
        // Equity 100 -> 50 -> 25: worst peak-to-trough decline is 75.
        Assert.Equal(75.0, sheet.MaxDrawdown!.Value, precision: 10);
        Assert.Equal(25.0 / 75.0, sheet.Romad!.Value, precision: 10);
    }

    [Fact]
    public void Reason_breakdown_groups_by_code()
    {
        var sheet = Build(decisions:
        [
            Decision(reason: "tp-first"),
            Decision(reason: "tp-first"),
            Decision(reason: "sl-first"),
            Decision(reason: ""),
        ]);

        Assert.Equal(2, sheet.ReasonBreakdown["tp-first"]);
        Assert.Equal(1, sheet.ReasonBreakdown["sl-first"]);
        Assert.Equal(1, sheet.ReasonBreakdown["unknown"]);
    }

    [Fact]
    public void Confidence_histogram_has_ten_bins_and_clamps()
    {
        var sheet = Build(decisions:
        [
            Decision(confidence: 0.0),
            Decision(confidence: 0.05),
            Decision(confidence: 0.55),
            Decision(confidence: 1.0),
            Decision(confidence: 1.5), // clamps into the top bin
            Decision(confidence: -0.5), // clamps into the bottom bin
        ]);

        var bins = sheet.ConfidenceHistogram.ToList();
        Assert.Equal(10, bins.Count);
        Assert.Equal(6, bins.Sum());
        Assert.Equal(3, bins[0]);
        Assert.Equal(1, bins[5]);
        Assert.Equal(2, bins[9]);
    }

    [Fact]
    public void Undefined_metrics_are_null_never_nan_or_infinity()
    {
        // All winners: no losing leg, so profit factor is undefined.
        var allWinners = Build(decisions: [Decision(expectedValue: 1.0), Decision(expectedValue: 2.0)]);
        Assert.Null(allWinners.ProfitFactor);
        Assert.NotNull(allWinners.Sharpe);

        // A single trade: Sharpe needs at least two points.
        var single = Build(decisions: [Decision(expectedValue: 1.0)]);
        Assert.Null(single.Sharpe);

        // A flat series: zero variance kills Sharpe, zero drawdown kills ROMAD.
        var flat = Build(decisions: [Decision(expectedValue: 0.0), Decision(expectedValue: 0.0)]);
        Assert.Null(flat.Sharpe);
        Assert.Equal(0.0, flat.MaxDrawdown);
        Assert.Null(flat.Romad);

        foreach (var value in new[]
            {
                allWinners.WinRate, allWinners.ExpectancyAtr, allWinners.MaxDrawdown, allWinners.Romad,
                single.WinRate, single.ExpectancyAtr, single.MaxDrawdown,
                flat.WinRate, flat.ExpectancyAtr,
            })
        {
            if (value.HasValue)
            {
                Assert.False(double.IsNaN(value.Value));
                Assert.False(double.IsInfinity(value.Value));
            }
        }
    }
}
