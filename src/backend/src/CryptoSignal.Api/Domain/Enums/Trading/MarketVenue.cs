using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// Where a candle or a fill came from. Recorded on both, because a decision is only replayable if the
/// prices it used can be attributed to a venue.
/// </summary>
/// <remarks>
/// There is deliberately no "any" or "default" member and no fallback between members. Silently
/// substituting one venue's prices for another's is the antipattern the safety policy names; a missing
/// window faults the bot instead.
/// </remarks>
public enum MarketVenue
{
    /// <summary>Recorded candles replayed from disk. Deterministic, for tests and backfills.</summary>
    [Display(Name = "Replay")] Replay = 1,

    /// <summary>The Binance spot testnet — the only venue reachable from inside the containers.</summary>
    [Display(Name = "Binance testnet")] BinanceTestnet = 2,

    /// <summary>Binance production. Reachable only where egress exists.</summary>
    [Display(Name = "Binance mainnet")] BinanceMainnet = 3,
}
