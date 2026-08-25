namespace CryptoSignal.Api.Application.Trading.Models;

/// <summary>One closed candle as a market-data source reports it. Prices are exact.</summary>
/// <remarks>
/// Decimal throughout, for the same reason the gRPC boundary carries prices as strings: a candle that
/// arrives here becomes both a persisted <c>MarketCandle</c> row and an entry price on a stored order
/// intent, and a round trip through <c>double</c> cannot promise those two agree
/// (<c>docs/LIVE_TRADING_SAFETY.md</c>). <c>QuoteVolume</c> and <c>TradeCount</c> are nullable because
/// not every venue reports them, and a zero would be a claim rather than an absence.
/// </remarks>
public sealed record MarketCandleData(
    DateTimeOffset OpenTime,
    DateTimeOffset CloseTime,
    decimal Open,
    decimal High,
    decimal Low,
    decimal Close,
    decimal Volume,
    decimal? QuoteVolume = null,
    int? TradeCount = null);
