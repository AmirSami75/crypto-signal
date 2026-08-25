using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// The immutable record of one thing the engine was asked and answered, for one bot on one closed
/// candle. Everything downstream — the intent, the risk decision, the order, the fill — hangs off this
/// row, and the causal chain the safety policy requires begins here.
/// </summary>
/// <remarks>
/// <para>
/// The unique index on <c>(BotId, CandleOpenTime)</c> is the load-bearing constraint of the whole
/// design: it is the database enforcing "at most one decision per bot per candle", which is what makes
/// a re-delivered tick a no-op instead of a second order. It is not an optimisation — it is the
/// idempotency guarantee, and the intent's deterministic client-order id is built on top of it.
/// </para>
/// <para>
/// <see cref="CandleWindowDigest"/> is the SHA-256 the engine computed over the exact candle window it
/// consumed. Storing it lets an audit prove the decision was made on the candles the row claims, and a
/// mismatch on replay is a tampering signal, not a rounding difference.
/// </para>
/// </remarks>
public class StrategyDecision : BaseEntity
{
    #region Provenance

    /// <summary>The bot this decision was made for.</summary>
    public Guid BotId { get; set; }

    /// <summary>The run during which it was made.</summary>
    public Guid? BotRunId { get; set; }

    /// <summary>Which venue class this decision belongs to. Filtered on every read.</summary>
    public OperatingMode OperatingMode { get; set; }

    /// <summary>Symbol and interval, copied so the decision reads without a join.</summary>
    public string Symbol { get; set; } = string.Empty;
    public string Interval { get; set; } = string.Empty;

    /// <summary>Open time of the candle decided on. Half of the idempotency key.</summary>
    public DateTime CandleOpenTime { get; set; }

    /// <summary>SHA-256 over the candle window the engine consumed.</summary>
    public string CandleWindowDigest { get; set; } = string.Empty;

    #endregion

    #region What the engine answered

    /// <summary>The action the engine advised.</summary>
    public BotDecisionAction Action { get; set; }

    /// <summary>The direction it points, if any.</summary>
    public TradeDirection Direction { get; set; }

    /// <summary>One token from the engine's reason-code vocabulary.</summary>
    public string ReasonCode { get; set; } = string.Empty;

    /// <summary>Calibrated probability the chosen side reaches take-profit before stop-loss.</summary>
    public double Confidence { get; set; }

    /// <summary>Long-side confidence, always reported.</summary>
    public double LongConfidence { get; set; }

    /// <summary>Short-side confidence, always reported.</summary>
    public double ShortConfidence { get; set; }

    /// <summary>Expected value per unit, in ATR units. The sizing input the risk engine reads.</summary>
    public double ExpectedValue { get; set; }

    /// <summary>P(take-profit first) from the triple-barrier head.</summary>
    public double ProbabilityTakeProfitFirst { get; set; }

    /// <summary>P(stop-loss first).</summary>
    public double ProbabilityStopLossFirst { get; set; }

    /// <summary>P(neither barrier inside the horizon).</summary>
    public double ProbabilityTimeout { get; set; }

    #endregion

    #region Levels (exact prices)

    /// <summary>Entry price the engine quoted, or null on a HOLD.</summary>
    public decimal? EntryPrice { get; set; }

    /// <summary>Take-profit price, or null on a HOLD.</summary>
    public decimal? TakeProfitPrice { get; set; }

    /// <summary>Stop-loss price, or null on a HOLD.</summary>
    public decimal? StopLossPrice { get; set; }

    /// <summary>ATR at the decision candle, in price units. The bracket's unit of measure.</summary>
    public decimal? Atr { get; set; }

    /// <summary>Risk-reward ratio the levels imply.</summary>
    public double? RiskRewardRatio { get; set; }

    /// <summary>Take-profit distance in ATR units, as the model consumed it.</summary>
    public double? TakeProfitAtr { get; set; }

    /// <summary>Stop-loss distance in ATR units.</summary>
    public double? StopLossAtr { get; set; }

    #endregion

    #region Model and validity

    public string ModelId { get; set; } = string.Empty;
    public string ModelVersion { get; set; } = string.Empty;
    public DateTime? ModelTrainedAt { get; set; }

    /// <summary>True when the engine answered from the pooled cross-symbol model.</summary>
    public bool UsedWildcardModel { get; set; }

    /// <summary>
    /// True when a requested barrier fell outside the model's fitted ATR span, making the expected
    /// value an extrapolation. The risk engine gates on this flag, never on the warning prose.
    /// </summary>
    public bool BarrierExtrapolated { get; set; }

    /// <summary>Advisory text from the engine. Never an execution instruction.</summary>
    public string? Warning { get; set; }

    /// <summary>When the signal goes stale — the next candle boundary, unless a stricter limit applies.</summary>
    public DateTime? ValidUntil { get; set; }

    /// <summary>The engine's own request id, for correlating logs across the boundary.</summary>
    public string? EngineRequestId { get; set; }

    /// <summary>How long the engine took, milliseconds. Observability, not control.</summary>
    public double ProcessingMilliseconds { get; set; }

    #endregion
}
