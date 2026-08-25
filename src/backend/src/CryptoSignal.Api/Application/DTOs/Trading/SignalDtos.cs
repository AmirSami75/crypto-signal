using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.DTOs.Trading;

/// <summary>
/// A request for one on-demand signal: a market, and the bet the caller is considering.
/// </summary>
/// <remarks>
/// <para>
/// <b>The caller does not send candles.</b> It sends the market, and the API fetches the closed-candle
/// window from the configured venue itself. That is not a convenience: a caller-supplied window is a
/// caller-supplied answer — include the still-forming candle, or reorder two rows, and the model's
/// features quietly describe a market that never existed. The orchestrator owns the window so the
/// signal is reproducible from the recorded venue data rather than from whatever a browser posted.
/// </para>
/// <para>
/// Both percentages are percent of the entry price and both must be greater than zero. They are inputs
/// to the model, not a filter on its output: 2% / 1% and 1% / 2% on the same candle are two different
/// bets and get two separately calibrated answers.
/// </para>
/// </remarks>
public sealed record SignalRequestDto
{
    /// <summary>Exchange symbol, e.g. <c>BTCUSDT</c>. Case is normalised.</summary>
    public string Symbol { get; init; } = string.Empty;

    /// <summary>Candle interval, e.g. <c>1h</c>.</summary>
    public string Interval { get; init; } = string.Empty;

    /// <summary>Take-profit distance as a percent of entry. Greater than zero.</summary>
    public decimal TakeProfitPercent { get; init; }

    /// <summary>Stop-loss distance as a percent of entry. Greater than zero.</summary>
    public decimal StopLossPercent { get; init; }

    /// <summary>
    /// Whether a SHORT answer is acceptable. False still reports the short side's confidence — the
    /// caller can see the edge it declined — it only stops the returned direction from being SHORT.
    /// </summary>
    public bool AllowShort { get; init; }

    /// <summary>Holding limit in candles. Zero uses the engine's configured default.</summary>
    public uint MaxHoldingPeriods { get; init; }

    /// <summary>Calibrated confidence floor. Zero uses the engine's configured default.</summary>
    public double MinimumConfidence { get; init; }

    /// <summary>
    /// Venue to read candles from. Null uses the deployment's configured signal venue. An explicit
    /// value is honoured exactly — there is no fallback to another venue if it cannot answer.
    /// </summary>
    public MarketVenue? Venue { get; init; }
}

/// <summary>The prices a bet resolves to, in the units the model consumed.</summary>
public sealed record SignalLevelsDto(
    decimal EntryPrice,
    decimal TakeProfitPrice,
    decimal StopLossPrice,
    decimal Atr,
    double RiskRewardRatio,
    double TakeProfitAtr,
    double StopLossAtr);

/// <summary>Probability each triple-barrier outcome is reached first. These sum to 1.</summary>
public sealed record SignalProbabilitiesDto(
    double TakeProfitFirst,
    double StopLossFirst,
    double Timeout);

/// <summary>
/// One signal, plus enough context to reproduce it.
/// </summary>
/// <remarks>
/// <para>
/// A signal is <b>evidence, not authorization</b> (<c>docs/LIVE_TRADING_SAFETY.md</c>). Nothing about
/// this response places, sizes, or approves an order, and the endpoint that returns it never will —
/// order submission happens only inside the bot scheduler.
/// </para>
/// <para>
/// Timestamps go out as raw UTC rather than the Persian display strings the auth DTOs use. A trading
/// client needs to compute a validity countdown and compare a candle time to its own clock, and both
/// of those need a machine-readable instant.
/// </para>
/// <para>
/// <see cref="BarrierExtrapolated"/> is the flag to read before trusting <see cref="ExpectedValue"/>:
/// it means the requested barrier fell outside the ATR span the model was fitted across, so the number
/// is an extension of the fitted surface rather than a measurement on it. A percent-denominated request
/// becomes a wide ATR bracket whenever the market is quiet, which is often.
/// </para>
/// </remarks>
public sealed record SignalResponseDto
{
    public string Symbol { get; init; } = string.Empty;
    public string Interval { get; init; } = string.Empty;

    /// <summary>Which venue's candles the answer was computed from.</summary>
    public MarketVenue Venue { get; init; }

    /// <summary>Closed candles fed to the model.</summary>
    public int CandleCount { get; init; }

    /// <summary>The bet as it was requested, echoed so a stored response is self-describing.</summary>
    public decimal TakeProfitPercent { get; init; }

    public decimal StopLossPercent { get; init; }

    public bool AllowShort { get; init; }

    /// <summary>LONG, SHORT, or FLAT. FLAT is a decision, not a failure to answer.</summary>
    public TradeDirection Direction { get; init; }

    /// <summary>Null when the direction is FLAT: there is no bracket for a position not taken.</summary>
    public SignalLevelsDto? Levels { get; init; }

    /// <summary>Calibrated probability the take-profit is reached first, for the reported direction.</summary>
    public double Confidence { get; init; }

    /// <summary>Both sides are always reported, including the one that was declined.</summary>
    public double LongConfidence { get; init; }

    public double ShortConfidence { get; init; }

    public SignalProbabilitiesDto Probabilities { get; init; } = new(0, 0, 0);

    public double ExpectedValue { get; init; }

    /// <summary>Open time of the newest closed candle the answer used.</summary>
    public DateTimeOffset? CandleOpenTime { get; init; }

    /// <summary>When the next candle closes. Past this instant the signal is stale, not merely old.</summary>
    public DateTimeOffset? ValidUntil { get; init; }

    public string ModelId { get; init; } = string.Empty;
    public string ModelVersion { get; init; } = string.Empty;
    public DateTimeOffset? ModelTrainedAt { get; init; }

    /// <summary>True when the pooled cross-symbol model answered rather than a dedicated one.</summary>
    public bool UsedWildcardModel { get; init; }

    /// <summary>SHA-256 of the candle window. Two identical digests must give identical answers.</summary>
    public string InputDigestSha256 { get; init; } = string.Empty;

    public string[] Rationale { get; init; } = [];

    /// <summary>Advisory prose. Never parsed, and never an execution instruction.</summary>
    public string Warning { get; init; } = string.Empty;

    /// <summary>See the remarks on this type before sizing anything on the expected value.</summary>
    public bool BarrierExtrapolated { get; init; }

    public double ProcessingMilliseconds { get; init; }
}
