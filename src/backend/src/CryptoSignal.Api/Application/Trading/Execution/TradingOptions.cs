namespace CryptoSignal.Api.Application.Trading.Execution;

/// <summary>
/// How the scheduler runs, bound from <c>Trading</c>. Separate from <c>Trading:Risk</c>: this section
/// decides <em>when</em> a bot is evaluated, never <em>whether</em> an order may be placed.
/// </summary>
/// <remarks>
/// <see cref="SchedulerEnabled"/> defaults to false. A deployment that has not been told to run bots does
/// not run them — the same fail-closed reading as the risk limits, applied to the loop itself. It is what
/// makes an accidental config-less deploy inert rather than active.
/// </remarks>
public sealed class TradingOptions
{
    public const string SectionName = "Trading";

    /// <summary>Whether the bot scheduler runs at all. False keeps every bot idle.</summary>
    public bool SchedulerEnabled { get; init; }

    /// <summary>
    /// How often the scheduler looks for due bots. Bots have their own cadence; this is the resolution at
    /// which those cadences are honoured, so it should be no coarser than the shortest one.
    /// </summary>
    public int PollSeconds { get; init; } = 15;

    /// <summary>Bots evaluated per cycle. Bounds the work one slow cycle can queue up.</summary>
    public int MaxBotsPerCycle { get; init; } = 20;

    /// <summary>Closed candles requested per evaluation. Must satisfy the engine's minimum window.</summary>
    public int CandleWindowSize { get; init; } = 300;

    /// <summary>
    /// How stale the newest closed candle may be, in intervals, before a tick faults instead of
    /// deciding. Mirrors Trading:Risk:MaxCandleAgeIntervals — that gate denies orders on stale data,
    /// this one refuses to even consult the model with it. Default tolerates two missed candles.
    /// </summary>
    public double MaxCandleAgeIntervals { get; init; } = 2.0;

    /// <summary>Wall-clock budget for one bot's tick. Exceeding it abandons the tick, not the bot.</summary>
    public int TickTimeoutSeconds { get; init; } = 60;

    /// <summary>
    /// Identifies this worker in the lease row. Defaults to the machine name, which is the container id in
    /// a compose deployment and is enough to tell two replicas apart.
    /// </summary>
    public string? LeaseOwner { get; init; }

    /// <summary>Seconds a heartbeat may lag before another worker may take the bot over.</summary>
    public int LeaseStaleSeconds { get; init; } = 180;

    /// <summary>
    /// Optional higher-timeframe interval (e.g. <c>4h</c>) that bots fetch and send as
    /// context candles so the engine can score MTF confluence features. Empty means
    /// no context is sent — the bot is scored on its own timeframe alone. The trainer
    /// must produce a model that includes MTF columns (controlled by
    /// <c>[features].mtf_context = true</c> in <c>config.toml</c>); sending context to
    /// a model not trained for it is a no-op the engine will warn about.
    /// </summary>
    public string? MtfContextInterval { get; init; }

    /// <summary>
    /// How many higher-TF candles to fetch when <see cref="MtfContextInterval"/> is set.
    /// The engine's <c>attach_higher_tf_features</c> reads the latest closed higher candle
    /// at each lower candle (backward join, no lookahead), so a handful suffices.
    /// </summary>
    public int MtfContextCandles { get; init; } = 48;
}
