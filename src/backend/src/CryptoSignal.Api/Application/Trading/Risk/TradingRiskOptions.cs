namespace CryptoSignal.Api.Application.Trading.Risk;

/// <summary>
/// Platform-wide risk ceilings, bound from <c>Trading:Risk</c>. Every default here denies.
/// </summary>
/// <remarks>
/// <para>
/// The defaults are not placeholders to be tuned later — they are the safe state. An unconfigured
/// deployment trades nothing: <see cref="AllowedSymbols"/> is empty, every maximum is zero, live
/// execution is off. <b>A zero or missing limit denies; it never means unlimited</b>
/// (<c>docs/LIVE_TRADING_SAFETY.md</c>). That inversion is the whole point: a config file that fails to
/// load, a section that is renamed, a typo in a key — each of those becomes "place no orders" rather
/// than "place orders without a ceiling".
/// </para>
/// <para>
/// These are ceilings, not the effective limits. A bot's own limits are applied too, and the tighter of
/// the two wins on every check.
/// </para>
/// </remarks>
public sealed class TradingRiskOptions
{
    public const string SectionName = "Trading:Risk";

    /// <summary>
    /// Master switch for real-money execution. False here means a LIVE bot is denied no matter what
    /// else is configured, and it stays false: gates 6-8 of the safety policy are not implemented.
    /// </summary>
    public bool AllowLiveExecution { get; init; }

    /// <summary>Modes the scheduler will act for at all. Empty denies every mode.</summary>
    public string[] EnabledOperatingModes { get; init; } = [];

    /// <summary>Tradable symbols. Empty denies everything — there is no "all symbols" value.</summary>
    public string[] AllowedSymbols { get; init; } = [];

    /// <summary>
    /// Spot only. Short intents are refused while true, because a spot account cannot borrow to sell
    /// what it does not hold — the refusal is arithmetic, not policy.
    /// </summary>
    public bool SpotOnly { get; init; } = true;

    /// <summary>Leverage ceiling. 1 is unleveraged and is the only value spot supports.</summary>
    public int MaxLeverage { get; init; } = 1;

    /// <summary>Whether a SHORT may ever be placed. Off by default and irrelevant while spot-only.</summary>
    public bool AllowShorting { get; init; }

    /// <summary>Notional ceiling per order, in quote currency. Zero denies.</summary>
    public decimal MaxOrderNotional { get; init; }

    /// <summary>Total open exposure ceiling per bot, in quote currency. Zero denies.</summary>
    public decimal MaxPositionNotional { get; init; }

    /// <summary>Realised-loss ceiling per bot per UTC day. Zero denies.</summary>
    public decimal MaxDailyLoss { get; init; }

    /// <summary>Orders per bot per UTC day. Zero denies.</summary>
    public int MaxOrdersPerDay { get; init; }

    /// <summary>Concurrent open positions per bot. Zero denies.</summary>
    public int MaxConcurrentPositions { get; init; }

    /// <summary>
    /// How stale the newest closed candle may be, as a multiple of the bot's interval. Zero denies —
    /// a bot with no freshness bound would happily act on last week's window.
    /// </summary>
    public double MaxCandleAgeIntervals { get; init; }

    /// <summary>Consecutive tick failures before a bot is considered unhealthy. Zero denies.</summary>
    public int MaxConsecutiveFailures { get; init; }

    /// <summary>
    /// Model versions cleared for execution. Empty means "do not pin", which is deliberately permissive
    /// on <em>which</em> model answers — the version is still recorded on every decision, and a bot may
    /// pin its own. Unlike the numeric limits, an empty allowlist here cannot be a silent overspend.
    /// </summary>
    public string[] ApprovedModelVersions { get; init; } = [];
}
