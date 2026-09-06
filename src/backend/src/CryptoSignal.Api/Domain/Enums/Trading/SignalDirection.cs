namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// Which kind of trader owns a bot's execution path.
/// </summary>
public enum SignalDirection : byte
{
    Long = 1,
    Short = 2,
}

/// <summary>
/// How a bot gets its signals.
/// </summary>
public enum BotKind : byte
{
    /// <summary>Standard model-driven bot (the default; uses the ML engine advisor).</summary>
    Model = 0,

    /// <summary>
    /// A scanner-mode bot: consumes signals emitted by the market scanner's strategy league
    /// rather than consulting the pooled model directly. It still routes through the
    /// full risk → intent → order pipeline unchanged.
    /// </summary>
    Scanner = 1,
}
