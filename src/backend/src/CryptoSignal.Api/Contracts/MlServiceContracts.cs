using System.Globalization;

namespace CryptoSignal.Api.Contracts;

/// <summary>
/// The .NET view of the ML engine's contract. One rule shapes every type in this file: <b>money is
/// <see cref="decimal"/>, never <see cref="double"/></b>.
/// </summary>
/// <remarks>
/// The wire carries prices as decimal strings for exactly this reason — see the header of
/// <c>ml_engine.proto</c> and the "no floating-point monetary state" rule in
/// <c>docs/LIVE_TRADING_SAFETY.md</c>. The audit chain has to be able to prove that the price the
/// engine computed is the price the database recorded, and a round trip through <c>double</c> cannot
/// promise that. Only dimensionless quantities — probabilities, ratios, ATR multiples, timings —
/// are floating point here, because none of them is ever stored as money or compared for equality.
/// </remarks>
public static class MlWire
{
    /// <summary>
    /// Reads a price off the wire, or throws.
    /// </summary>
    /// <remarks>
    /// Invariant culture, deliberately and non-negotiably: this application runs in a Persian locale,
    /// and a culture-sensitive parse would read "1.5" as fifteen wherever the decimal separator is a
    /// comma. Throwing rather than returning zero is the other half — a malformed price is an engine
    /// bug, and a silent zero would become an entry price of zero in a stored order intent, which is
    /// both a valid <c>decimal</c> and a catastrophe.
    /// </remarks>
    public static decimal Money(string value, string field)
    {
        if (!decimal.TryParse(
                value,
                NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint,
                CultureInfo.InvariantCulture,
                out var parsed))
        {
            throw new MlServiceException(
                "MalformedPrice",
                $"The ML engine returned '{value}' for {field}, which is not a decimal number.");
        }

        return parsed;
    }

    /// <summary>Writes a price onto the wire in the fixed-point form the engine parses.</summary>
    public static string Money(decimal value) =>
        value.ToString("0.########", CultureInfo.InvariantCulture);
}

/// <summary>Which way a bet points. Mirrors <c>TradeDirection</c> on the wire.</summary>
public enum MlDirection
{
    /// <summary>Not set. Distinct from <see cref="Flat"/>, which is a decision.</summary>
    Unspecified = 0,
    Long = 1,
    Short = 2,

    /// <summary>No position, and no reason to open one.</summary>
    Flat = 3,
}

/// <summary>What the engine advises doing next. Mirrors <c>BotAction</c> on the wire.</summary>
public enum MlBotAction
{
    Unspecified = 0,
    Hold = 1,
    Open = 2,
    Close = 3,

    /// <summary>Keep the position, move the bracket to the returned levels.</summary>
    AdjustBracket = 4,
}

/// <summary>One closed candle. Prices are exact.</summary>
public sealed record MlCandle(
    DateTimeOffset OpenTime,
    decimal Open,
    decimal High,
    decimal Low,
    decimal Close,
    decimal Volume);

/// <summary>
/// What the caller is betting. The model is barrier-conditional, so these distances are inputs to it
/// rather than a filter on its output: any take-profit / stop-loss pair gets a probability calibrated
/// for that pair.
/// </summary>
/// <remarks>
/// Both percentages are percent of the entry price and must be greater than zero — a barrier at the
/// entry is touched immediately. <c>AllowShort</c> false still reports the short side's confidence;
/// it only stops the direction from being SHORT. <c>MaxHoldingPeriods</c> and
/// <c>MinimumConfidence</c> use the engine's configured default when left at zero, which is safe for
/// these two only because zero is not a usable value for either: nobody asks for a holding limit of
/// zero candles or a confidence floor of zero.
/// </remarks>
public sealed record MlTradeParameters(
    decimal TakeProfitPercent,
    decimal StopLossPercent,
    bool AllowShort,
    uint MaxHoldingPeriods = 0,
    double MinimumConfidence = 0);

/// <summary>The prices a bet resolves to, plus the same barriers in the units the model consumed.</summary>
public sealed record MlTradeLevels(
    decimal EntryPrice,
    decimal TakeProfitPrice,
    decimal StopLossPrice,
    decimal Atr,
    double RiskRewardRatio,
    double TakeProfitAtr,
    double StopLossAtr);

/// <summary>
/// Probability that each triple-barrier outcome is reached FIRST, for the direction reported
/// alongside it. These sum to 1.
/// </summary>
public sealed record MlBarrierProbabilities(
    double TakeProfitFirst,
    double StopLossFirst,
    double Timeout);

/// <summary>An open position as the orchestrator sees it. The engine holds no position state.</summary>
/// <remarks>
/// The two bracket prices are the orders actually working at the venue, and either may be null: a bot
/// whose stop lives at the venue and whose take-profit does not is a real configuration, and the
/// engine falls back to the configured percentage for whichever half is missing. <c>BarsHeld</c> is
/// closed candles elapsed since the position opened.
/// </remarks>
public sealed record MlOpenPosition(
    MlDirection Direction,
    decimal EntryPrice,
    decimal Quantity,
    DateTimeOffset? OpenedAt,
    decimal? TakeProfitPrice,
    decimal? StopLossPrice,
    uint BarsHeld);

/// <summary>One point on a model's measured confidence distribution.</summary>
public sealed record MlConfidenceReach(double Threshold, double Share);

/// <summary>A market the engine can answer for.</summary>
public sealed record MlSupportedMarket(
    string Symbol,
    string Interval,
    string ModelId,
    string ModelVersion,
    bool IsWildcard);

public sealed record MlServiceCapabilities(
    string Service,
    string ServiceVersion,
    string ProtocolVersion,
    string[] Capabilities,
    string[] SupportedOperations,
    bool ModelReady,
    uint MinimumCandles,
    uint MaximumCandles,
    MlSupportedMarket[] SupportedMarkets,
    bool WildcardModelReady,
    string OperatingMode);

/// <remarks>
/// <c>ConfidenceCeiling</c> is the highest confidence this model produced on held-out data, or 0 when
/// the training run did not measure it. A minimum confidence above that ceiling can never be met, so
/// what it filters out is every signal — silence, not safety. <c>ConfidenceReach</c> prices the same
/// trade-off in coverage: what share of held-out candles cleared each threshold.
/// </remarks>
public sealed record MlModelInfo(
    bool Ready,
    string ModelId,
    string ModelVersion,
    string ProjectVersion,
    string Symbol,
    string Interval,
    DateTimeOffset? TrainedAt,
    uint FeatureCount,
    bool IsWildcard,
    string LabelScheme,
    string CalibrationMethod,
    uint DefaultMaxHoldingPeriods,
    double MinimumBarrierAtr,
    double MaximumBarrierAtr,
    double ConfidenceCeiling,
    MlConfidenceReach[] ConfidenceReach);

public sealed record MlSignalRequest(
    string Symbol,
    string Interval,
    IReadOnlyList<MlCandle> Candles,
    MlTradeParameters Parameters,
    string? ExpectedModelVersion = null,
    string? RequestId = null);

/// <remarks>
/// <c>BarrierExtrapolated</c> is true when a requested barrier fell outside the ATR span the model was
/// fitted across, which makes <c>ExpectedValue</c> an extension of the fitted surface rather than a
/// measurement on it. The risk engine gates on this flag and never on the prose in <c>Warning</c>: a
/// percent-denominated request becomes a wide ATR bracket whenever the market is quiet, which is
/// often, and sizing on an extrapolated expected value is sizing on an artefact.
/// </remarks>
public sealed record MlSignal(
    string RequestId,
    MlDirection Direction,
    MlTradeLevels? Levels,
    double Confidence,
    MlBarrierProbabilities Probabilities,
    double ExpectedValue,
    double LongConfidence,
    double ShortConfidence,
    string Symbol,
    string Interval,
    DateTimeOffset? CandleOpenTime,
    DateTimeOffset? ValidUntil,
    string ModelId,
    string ModelVersion,
    DateTimeOffset? ModelTrainedAt,
    bool UsedWildcardModel,
    string InputDigestSha256,
    string[] Rationale,
    string Warning,
    double ProcessingMilliseconds,
    bool BarrierExtrapolated);

public sealed record MlBotDecisionRequest(
    string BotId,
    string Symbol,
    string Interval,
    IReadOnlyList<MlCandle> Candles,
    MlTradeParameters Parameters,
    MlOpenPosition? Position = null,
    string? ExpectedModelVersion = null,
    string? RequestId = null,
    IReadOnlyList<MlCandle>? ContextCandles = null,
    string? ContextInterval = null);

/// <remarks>
/// <c>ReasonCode</c> is one token from a fixed vocabulary the orchestrator switches on:
/// <c>no_edge</c>, <c>confidence_below_minimum</c>, <c>take_profit_touched</c>,
/// <c>stop_loss_touched</c>, <c>max_holding_periods_reached</c>, <c>direction_reversed</c>,
/// <c>short_not_allowed</c>, <c>trailing_stop_advanced</c>. <c>Levels</c> carries the bracket to place
/// on OPEN and ADJUST_BRACKET, and on CLOSE the bracket that was in force.
/// </remarks>
public sealed record MlBotDecision(
    string RequestId,
    MlBotAction Action,
    MlDirection Direction,
    MlTradeLevels? Levels,
    double Confidence,
    MlBarrierProbabilities Probabilities,
    double ExpectedValue,
    string ReasonCode,
    string[] Rationale,
    string Symbol,
    string Interval,
    DateTimeOffset? CandleOpenTime,
    DateTimeOffset? ValidUntil,
    string ModelId,
    string ModelVersion,
    DateTimeOffset? ModelTrainedAt,
    bool UsedWildcardModel,
    string InputDigestSha256,
    string Warning,
    double ProcessingMilliseconds,
    bool BarrierExtrapolated);

public sealed record DependencyHealth(
    string Name,
    string Status,
    string? Detail = null);

/// <summary>
/// One resolved trade, reported to the engine's online-learning sample store. Prices and pnl cross
/// as decimal strings per the proto contract; the engine stores the sample for a future training run.
/// </summary>
public sealed record MlTradeOutcome(
    string BotId,
    string Symbol,
    string Interval,
    string ModelId,
    string ModelVersion,
    MlDirection Direction,
    IReadOnlyList<MlCandle> Candles,
    decimal TakeProfitPercent,
    decimal StopLossPercent,
    string CloseReason,
    decimal RealizedPnl,
    uint BarsHeld,
    DateTimeOffset DecisionCandleOpenTime,
    DateTimeOffset ClosedAt,
    string? RequestId = null);

public sealed record MlTradeOutcomeAck(
    string RequestId,
    string Status,
    uint SamplesStored,
    bool TrainingTriggered);

public sealed record MlMarketTrainingStatus(
    string Symbol,
    string Interval,
    uint SamplesStored,
    uint SamplesSinceTraining,
    string? LastTrainedAt,
    string? LastChallengerVersion,
    string LastVerdict,
    string LastVerdictReason,
    bool TrainingInProgress);

public sealed record MlTrainingStatus(
    string RequestId,
    bool OnlineLearningEnabled,
    IReadOnlyList<MlMarketTrainingStatus> Markets);

/// <summary>One symbol's candle window for a market scan.</summary>
public sealed record MlScanSymbol(
    string Symbol,
    IReadOnlyList<MlCandle> Candles);

/// <summary>
/// A strategy spec: which zoo strategy to run and the ATR-based bracket to attach to its signal.
/// </summary>
public sealed record MlScanStrategy(
    string Name,
    double TakeProfitAtr,
    double StopLossAtr);

/// <summary>One strategy's signal (or lack thereof) for one symbol.</summary>
public sealed record MlScanResult(
    string Symbol,
    string Strategy,
    string Direction,  // "LONG" | "SHORT" | ""
    double Confidence,
    string Reason,
    string Warning);

public sealed class MlServiceException(
    string errorCode,
    string message,
    Exception? innerException = null) : Exception(message, innerException)
{
    public string ErrorCode { get; } = errorCode;
}
