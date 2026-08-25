namespace CryptoSignal.Api.Application.Options;

/// <summary>
/// The simulated venue's parameters, bound from <c>Trading:Paper</c>. These describe a fill that never
/// happens, so nothing here can lose money — but they decide whether a PAPER result is worth reading.
/// </summary>
/// <remarks>
/// Both costs default to non-zero on purpose. A simulator with zero fees and zero slippage reports a
/// profit the market would not have paid, and that number is what an operator uses to decide whether to
/// go live. Free and frictionless is the one setting that makes PAPER actively misleading.
/// </remarks>
public sealed class PaperBrokerOptions
{
    public const string SectionName = "Trading:Paper";

    /// <summary>
    /// Adverse price movement charged on every simulated fill, in basis points: a buy fills above the
    /// reference, a sell below it. Never favourable — a simulator that sometimes fills better than the
    /// reference is modelling luck, not a venue.
    /// </summary>
    public int SlippageBps { get; init; } = 5;

    /// <summary>Taker fee charged on the filled notional, in basis points, in the quote asset.</summary>
    public int FeeBps { get; init; } = 10;

    /// <summary>
    /// The simulated free balance reported for any quote asset.
    /// </summary>
    /// <remarks>
    /// A constant, and deliberately so: the paper broker holds no ledger, and inventing a depleting
    /// balance without one would produce a number that disagrees with the positions actually recorded.
    /// Paper profit and loss is read from <c>BotPositions</c>, which is the real record; this value only
    /// feeds the risk engine's balance check, and the notional and exposure ceilings are what actually
    /// bound a paper bot.
    /// </remarks>
    public decimal QuoteBalance { get; init; } = 10_000m;
}
