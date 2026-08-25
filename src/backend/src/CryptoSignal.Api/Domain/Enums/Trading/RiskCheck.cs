using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// The pre-trade checks the risk engine evaluates, one member per check required by
/// <c>docs/LIVE_TRADING_SAFETY.md</c> §"Required pre-trade checks".
/// </summary>
/// <remarks>
/// <para>
/// Typed rather than free prose because a denial has to be machine-readable: the dashboard groups by
/// check, monitoring alerts on rejection rates per check, and a test asserts that a specific check —
/// not merely "something" — denied a specific order. A string column would let the same check be
/// spelled two ways and quietly break both.
/// </para>
/// <para>
/// All checks are evaluated against one consistent snapshot, and a check that cannot complete denies
/// the order. There is no member for "passed with a warning": the outcome space is allow or deny.
/// </para>
/// </remarks>
public enum RiskCheck
{
    /// <summary>1. Operating mode and strategy are enabled.</summary>
    [Display(Name = "Mode and strategy enabled")] ModeAndStrategyEnabled = 1,

    /// <summary>2. The deployed model version is approved and not retired.</summary>
    [Display(Name = "Model version approved")] ModelVersionApproved = 2,

    /// <summary>3. The signal belongs to the intended model, instrument, interval and completed candle.</summary>
    [Display(Name = "Signal provenance")] SignalProvenance = 3,

    /// <summary>4. The signal has not already produced an order intent.</summary>
    [Display(Name = "Signal not already acted on")] SignalNotAlreadyActedOn = 4,

    /// <summary>5. Signal, candle, price, balance, position, fee and instrument metadata are fresh.</summary>
    [Display(Name = "Data freshness")] DataFreshness = 5,

    /// <summary>6. The market is allowlisted and currently tradable.</summary>
    [Display(Name = "Market allowlisted and tradable")] MarketAllowlistedAndTradable = 6,

    /// <summary>7. Side, type, quantity, price, precision and time-in-force are supported.</summary>
    [Display(Name = "Order parameters supported")] OrderParametersSupported = 7,

    /// <summary>8. Estimated notional is above the exchange minimum and below the configured maximum.</summary>
    [Display(Name = "Notional within bounds")] NotionalWithinBounds = 8,

    /// <summary>9. Resulting position, concentration, gross exposure and quote reserve remain within limits.</summary>
    [Display(Name = "Exposure within limits")] ExposureWithinLimits = 9,

    /// <summary>10. Daily realized/unrealized loss and drawdown remain within limits.</summary>
    [Display(Name = "Loss and drawdown within limits")] LossAndDrawdownWithinLimits = 10,

    /// <summary>11. Order frequency, turnover, consecutive-loss and duplicate-intent limits are satisfied.</summary>
    [Display(Name = "Frequency and turnover within limits")] FrequencyAndTurnoverWithinLimits = 11,

    /// <summary>12. Sufficient available balance after existing reservations and open orders.</summary>
    [Display(Name = "Sufficient balance")] SufficientBalance = 12,

    /// <summary>13. Exchange connectivity and reconciliation state are healthy.</summary>
    [Display(Name = "Connectivity and reconciliation healthy")] ConnectivityAndReconciliationHealthy = 13,

    /// <summary>14. The global, exchange, account and strategy kill switches are clear.</summary>
    [Display(Name = "Kill switches clear")] KillSwitchesClear = 14,

    /// <summary>15. Required human approval is valid, unexpired and tied to the exact order preview.</summary>
    [Display(Name = "Human approval valid")] HumanApprovalValid = 15,

    /// <summary>
    /// Not one of the policy's checks: the engine reported that a requested barrier fell outside the
    /// ATR span the model was fitted across, so its expected value is an extrapolation. Sizing on an
    /// extrapolated expected value is sizing on an artefact, so it denies like any other check.
    /// </summary>
    [Display(Name = "Barrier within fitted range")] BarrierWithinFittedRange = 16,
}
