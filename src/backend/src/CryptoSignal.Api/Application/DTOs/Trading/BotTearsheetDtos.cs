namespace CryptoSignal.Api.Application.DTOs.Trading;

/// <summary>
/// The window the tearsheet covers: the last <see cref="Days"/> days up to <see cref="To"/>.
/// </summary>
public sealed record BotTearsheetPeriodDto(
    int Days,
    DateTime From,
    DateTime To);

/// <summary>
/// A lumibot-style performance summary for one bot over <see cref="Period"/>.
/// </summary>
/// <remarks>
/// <para>
/// Trade statistics come from closed <c>BotPosition.RealizedPnl</c> figures whenever fills exist in the
/// window (<see cref="FillsIncluded"/> is true). Positions accumulate P&amp;L from recorded fills, so
/// they are the durable per-trade record — fills themselves are executions, not closed trades.
/// </para>
/// <para>
/// When no fills exist in the window the endpoint still answers, but the trade statistics fall back to
/// the entry decisions' <c>ExpectedValue</c> (in ATR units) as a proxy series, and
/// <see cref="FillsIncluded"/> is false so no consumer mistakes the proxy for realised trading.
/// </para>
/// <para>
/// Nullable metrics are null when they are undefined, never NaN or Infinity: no trades, no losing
/// trades (profit factor), fewer than two trades or zero variance (Sharpe), zero drawdown (ROMAD).
/// </para>
/// </remarks>
public sealed record BotTearsheetDto(
    Guid BotId,
    BotTearsheetPeriodDto Period,
    int Decisions,
    int Entries,
    bool FillsIncluded,
    double? WinRate,
    double? ExpectancyAtr,
    double? ProfitFactor,
    double? Sharpe,
    double? MaxDrawdown,
    double? Romad,
    IReadOnlyDictionary<string, int> ReasonBreakdown,
    IReadOnlyList<int> ConfidenceHistogram);
