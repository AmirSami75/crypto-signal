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

    /// <summary>
    /// Bitunix USDT-margined futures. Their public OpenAPI is futures-only
    /// (<c>fapi.bitunix.com</c>), double-SHA-256 signed — a different protocol family from the
    /// Binance venues, hence its own broker and kline source rather than a Binance subclass.
    /// </summary>
    [Display(Name = "Bitunix")] Bitunix = 4,

    /// <summary>
    /// Bybit USDT-margined futures, demo environment (<c>api-demo.bybit.com</c>). The v5 unified
    /// API with a full order lifecycle and virtual funds — the venue leveraged-futures work runs
    /// against, because it exercises real orders without real money.
    /// </summary>
    [Display(Name = "Bybit demo")] Bybit = 5,
}
