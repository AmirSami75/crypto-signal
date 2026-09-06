using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// A single signal emitted by the market scanner's strategy league.
/// The scanner creates proposals; it never places orders. A <see cref="TradingBot"/>
/// in <see cref="BotKind.Scanner"/> mode claims a signal and runs the existing
/// order pipeline against it.
/// </summary>
public sealed class ScannerSignal : BaseEntity
{
    public Guid ScanId { get; init; } = Guid.CreateVersion7();

    /// <summary>UTC time the scanner evaluated this signal.</summary>
    public DateTimeOffset SignalCreatedAt { get; init; } = DateTimeOffset.UtcNow;

    /// <summary>The symbol this signal is for, e.g. "BTCUSDT".</summary>
    public string Symbol { get; init; } = string.Empty;

    /// <summary>Interval the signal was computed on, e.g. "5m" or "1h".</summary>
    public string Interval { get; init; } = string.Empty;

    /// <summary>Strategy key from the strategy zoo, e.g. "rsi" or "bollinger".</summary>
    public string StrategyKey { get; init; } = string.Empty;

    /// <summary>Which way the signal points: LONG or SHORT.</summary>
    public SignalDirection Direction { get; init; } = SignalDirection.Long;

    /// <summary>Engine-reported confidence, 0..1. Indicator strategies report 1.0 (deterministic).</summary>
    public double Confidence { get; init; }

    /// <summary>Scoring component: |24h price change %| × log10(quote volume).</summary>
    public decimal Score { get; init; }

    /// <summary>The ATR (in price units) at the signal candle.</summary>
    public decimal AtrAtSignal { get; init; }

    /// <summary>Optional human-readable reason, e.g. "RSI crossed above oversold threshold".</summary>
    public string Reason { get; init; } = string.Empty;

    /// <summary>
    /// The bot that claimed this signal, or null when unclaimed.
    /// Claimed atomically so concurrent scanner-mode bots do not duplicate orders.
    /// </summary>
    public Guid? TakenByBotId { get; set; }
}
