using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// The immutable instruction to place one order, derived from exactly one <see cref="StrategyDecision"/>.
/// Its trading parameters never change after construction; the only thing that moves is
/// <see cref="Status"/>, and any change to symbol, side, size, price, type, account, model or mode
/// requires a new intent and a fresh risk decision rather than an edit to this one.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="ClientOrderId"/> is derived deterministically from the decision id, so a worker that
/// retries a tick constructs the <i>same</i> id and the venue — which dedupes on it — returns the
/// existing order instead of placing a second. That determinism, plus the unique index on the id, is
/// what makes "repeated worker delivery returns the existing order instead of submitting again" true
/// rather than aspirational.
/// </para>
/// <para>
/// The reference price is the price the decision assumed. Submission recomputes slippage against a
/// current snapshot and rejects if the gap exceeds the bot's tolerance — an intent is a preview, and a
/// preview is re-checked immediately before it becomes an order.
/// </para>
/// </remarks>
public class OrderIntent : BaseEntity
{
    #region Lineage

    /// <summary>The decision this intent realises. One intent per decision — enforced by a unique index.</summary>
    public Guid StrategyDecisionId { get; set; }

    /// <summary>The bot, copied for direct querying.</summary>
    public Guid BotId { get; set; }

    /// <summary>Which venue class this intent belongs to. Filtered on every read.</summary>
    public OperatingMode OperatingMode { get; set; }

    /// <summary>Deterministic, unique client order id. The idempotency key at the venue.</summary>
    public string ClientOrderId { get; set; } = string.Empty;

    #endregion

    #region The order

    public string Symbol { get; set; } = string.Empty;

    /// <summary>Which way the resulting position points. Distinct from <see cref="Side"/>.</summary>
    public TradeDirection Direction { get; set; }

    /// <summary>Book side. An open-long and a close-short are both <see cref="OrderSide.Buy"/>.</summary>
    public OrderSide Side { get; set; }

    public OrderType Type { get; set; }

    /// <summary>Base-asset quantity.</summary>
    public decimal Quantity { get; set; }

    /// <summary>Limit price, when the type carries one; null for a market order.</summary>
    public decimal? LimitPrice { get; set; }

    /// <summary>Take-profit price of the bracket this order establishes.</summary>
    public decimal? TakeProfitPrice { get; set; }

    /// <summary>Stop-loss price of the bracket.</summary>
    public decimal? StopLossPrice { get; set; }

    /// <summary>Time-in-force, explicit on every limit order.</summary>
    public TimeInForce? TimeInForce { get; set; }

    /// <summary>Reference price the decision assumed, for the slippage guard at submission.</summary>
    public decimal ReferencePrice { get; set; }

    /// <summary>The requested leverage. Always 1 for spot; explicitly applied by a futures broker.</summary>
    public int Leverage { get; set; } = 1;

    /// <summary>Estimated quote notional, fees and slippage included. Counts toward limits.</summary>
    public decimal EstimatedNotional { get; set; }

    #endregion

    #region State

    public OrderIntentStatus Status { get; set; } = OrderIntentStatus.Draft;

    /// <summary>Why the intent is where it is, when that needs explaining.</summary>
    public string? StatusReason { get; set; }

    /// <summary>When the intent was submitted to a venue, if it was.</summary>
    public DateTime? SubmittedAt { get; set; }

    /// <summary>When it reached a terminal state.</summary>
    public DateTime? CompletedAt { get; set; }

    #endregion
}
