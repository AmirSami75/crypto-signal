using CryptoSignal.Api.Application.Trading.Models;

namespace CryptoSignal.Api.Application.Trading.Instruments;

/// <summary>
/// The declared trading grid for the replay venue, which has no <c>exchangeInfo</c> endpoint to ask.
/// </summary>
/// <remarks>
/// <para>
/// These values mirror Binance spot as of the recorded data, so a replayed tick quantizes exactly as a
/// live one would. That equality is the whole reason the table is written out rather than approximated: a
/// deterministic test whose grid is finer than production would pass on order sizes production rejects.
/// </para>
/// <para>
/// A symbol with no entry <b>throws</b>. That is the fail-closed half — a generic fallback grid would be
/// either finer than the venue's (quantization becomes a no-op, and the test proves nothing) or coarser
/// (orders are silently resized). Adding a symbol here is a deliberate, reviewable act.
/// </para>
/// </remarks>
public static class ReplayInstrumentRules
{
    private static readonly Dictionary<string, InstrumentRules> Table = new(StringComparer.Ordinal)
    {
        ["BTCUSDT"] = Spot("BTC", "USDT", tick: 0.01m, step: 0.00001m, minQty: 0.00001m, maxQty: 9000m),
        ["ETHUSDT"] = Spot("ETH", "USDT", tick: 0.01m, step: 0.0001m, minQty: 0.0001m, maxQty: 90000m),
        ["BNBUSDT"] = Spot("BNB", "USDT", tick: 0.01m, step: 0.001m, minQty: 0.001m, maxQty: 90000m),
        ["SOLUSDT"] = Spot("SOL", "USDT", tick: 0.01m, step: 0.001m, minQty: 0.001m, maxQty: 900000m),
        ["XRPUSDT"] = Spot("XRP", "USDT", tick: 0.0001m, step: 1m, minQty: 1m, maxQty: 9222449m),
        ["ADAUSDT"] = Spot("ADA", "USDT", tick: 0.0001m, step: 0.1m, minQty: 0.1m, maxQty: 9222449m),
        ["DOGEUSDT"] = Spot("DOGE", "USDT", tick: 0.00001m, step: 1m, minQty: 1m, maxQty: 9222449m),

        // The synthetic pair the generated fixtures use. Round numbers so a hand-computed expectation in a
        // test is readable without a calculator.
        ["DEMOUSDT"] = Spot("DEMO", "USDT", tick: 0.01m, step: 0.001m, minQty: 0.001m, maxQty: 1000000m),
    };

    /// <summary>The grid for a replayed symbol, or throws naming what is declared.</summary>
    public static InstrumentRules For(string symbol)
    {
        var key = symbol.Trim().ToUpperInvariant();

        if (Table.TryGetValue(key, out var rules))
            return rules;

        throw new InstrumentRulesUnavailableException(
            $"The replay venue has no declared trading grid for '{key}'. Declared symbols: " +
            $"{string.Join(", ", Table.Keys.Order(StringComparer.Ordinal))}. Add an entry mirroring the " +
            "venue's own filters rather than trading against a guessed grid.");
    }

    /// <summary>Whether a symbol is declared, without throwing — for callers that only need to check.</summary>
    public static bool IsDeclared(string symbol) => Table.ContainsKey(symbol.Trim().ToUpperInvariant());

    private static InstrumentRules Spot(
        string baseAsset,
        string quoteAsset,
        decimal tick,
        decimal step,
        decimal minQty,
        decimal maxQty) =>
        new(
            Symbol: baseAsset + quoteAsset,
            BaseAsset: baseAsset,
            QuoteAsset: quoteAsset,
            TickSize: tick,
            StepSize: step,
            MinQuantity: minQty,
            MaxQuantity: maxQty,
            // Binance spot's USDT minimum at the time the data was recorded. Replay keeps it, so a test
            // that trades below the venue's floor fails here rather than in production.
            MinNotional: 5m,
            IsTradable: true,
            SupportsMarketOrders: true,
            PriceScale: MarketData.BinanceJson.ScaleOf(tick),
            QuantityScale: MarketData.BinanceJson.ScaleOf(step));
}
