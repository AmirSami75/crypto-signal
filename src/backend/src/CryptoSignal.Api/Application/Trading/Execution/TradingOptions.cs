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

    /// <summary>Wall-clock budget for one bot's tick. Exceeding it abandons the tick, not the bot.</summary>
    public int TickTimeoutSeconds { get; init; } = 60;

    /// <summary>
    /// Identifies this worker in the lease row. Defaults to the machine name, which is the container id in
    /// a compose deployment and is enough to tell two replicas apart.
    /// </summary>
    public string? LeaseOwner { get; init; }

    /// <summary>Seconds a heartbeat may lag before another worker may take the bot over.</summary>
    public int LeaseStaleSeconds { get; init; } = 180;
}
