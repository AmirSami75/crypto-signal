namespace CryptoSignal.Api.Application.Trading.Models;

/// <summary>
/// The venue's filters for one symbol: the grids a price and a quantity must land on, and the smallest
/// order it will accept.
/// </summary>
/// <remarks>
/// <para>
/// These are the venue's rules, not the platform's preferences, and they are the reason an order can be
/// rejected for reasons that have nothing to do with risk appetite. Checking them before submission
/// turns a venue rejection — which costs a round trip and leaves an intent in a failed state — into a
/// local denial with a named cause.
/// </para>
/// <para>
/// <see cref="IsTradable"/> is separate from "the symbol exists": a venue can list an instrument while
/// halting it, and a halted instrument must deny rather than be retried.
/// </para>
/// </remarks>
public sealed record InstrumentRules(
    string Symbol,
    string BaseAsset,
    string QuoteAsset,
    decimal TickSize,
    decimal StepSize,
    decimal MinQuantity,
    decimal MaxQuantity,
    decimal MinNotional,
    bool IsTradable,
    bool SupportsMarketOrders,
    int PriceScale,
    int QuantityScale)
{
    /// <summary>Rounds a price down onto the venue's tick grid.</summary>
    /// <remarks>
    /// Truncating rather than rounding to nearest, because rounding a stop-loss <em>outward</em> widens
    /// a risk the operator already sized. A tick is small; a silently loosened stop is not.
    /// </remarks>
    public decimal QuantizePrice(decimal price) =>
        TickSize <= 0 ? price : decimal.Truncate(price / TickSize) * TickSize;

    /// <summary>Rounds a quantity down onto the venue's step grid.</summary>
    /// <remarks>Down, never up: rounding up buys more than the notional the risk engine cleared.</remarks>
    public decimal QuantizeQuantity(decimal quantity) =>
        StepSize <= 0 ? quantity : decimal.Truncate(quantity / StepSize) * StepSize;

    /// <summary>True when the value already sits on the grid.</summary>
    public static bool IsOnGrid(decimal value, decimal grid) =>
        grid <= 0 || value % grid == 0m;
}
