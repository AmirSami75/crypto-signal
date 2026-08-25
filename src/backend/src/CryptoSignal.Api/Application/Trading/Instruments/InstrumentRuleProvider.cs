using System.Collections.Concurrent;
using System.Net.Http.Json;
using System.Text.Json;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Instruments;

/// <summary>
/// Resolves a symbol's trading grid: the venue's own filters where a venue can be asked, a declared table
/// where one cannot.
/// </summary>
/// <remarks>
/// <para>
/// Singleton, because the cache is the point. <c>exchangeInfo</c> is a large, slow, rate-limited response
/// and the grid changes on the order of months, so a per-tick fetch would spend the venue's rate budget on
/// a constant. Entries expire after <see cref="CacheTtl"/> so a listing change is picked up the same day
/// without a redeploy.
/// </para>
/// <para>
/// Where two filters bound the same quantity, the <b>tighter</b> one wins — <c>MARKET_LOT_SIZE</c> against
/// <c>LOT_SIZE</c>, the larger minimum, the smaller maximum, the coarser step. That direction is not
/// arbitrary: choosing the looser bound would let this class authorise an order the venue then refuses,
/// and every refusal costs a tick.
/// </para>
/// </remarks>
public sealed class InstrumentRuleProvider(
    IHttpClientFactory httpClientFactory,
    ILogger<InstrumentRuleProvider> logger) : IInstrumentRuleProvider, ISingletonSvcMarker
{
    private static readonly TimeSpan CacheTtl = TimeSpan.FromHours(6);

    private readonly ConcurrentDictionary<(MarketVenue Venue, string Symbol), CachedRules> cache = new();

    public async Task<InstrumentRules> GetRulesAsync(
        MarketVenue venue,
        string symbol,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(symbol))
            throw new InstrumentRulesUnavailableException("A symbol is required to resolve trading rules.");

        var key = (Venue: venue, Symbol: symbol.Trim().ToUpperInvariant());

        if (cache.TryGetValue(key, out var cached) && cached.ExpiresAt > DateTimeOffset.UtcNow)
            return cached.Rules;

        var rules = venue switch
        {
            MarketVenue.Replay => ReplayInstrumentRules.For(key.Symbol),
            MarketVenue.BinanceTestnet or MarketVenue.BinanceMainnet =>
                await FetchBinanceAsync(venue, key.Symbol, cancellationToken),
            _ => throw new InstrumentRulesUnavailableException(
                $"No instrument-rule source is configured for venue {venue}."),
        };

        cache[key] = new CachedRules(rules, DateTimeOffset.UtcNow.Add(CacheTtl));
        return rules;
    }

    private async Task<InstrumentRules> FetchBinanceAsync(
        MarketVenue venue,
        string symbol,
        CancellationToken cancellationToken)
    {
        var client = httpClientFactory.CreateClient(TradingHttpClients.ForVenue(venue));

        JsonDocument document;
        try
        {
            // Asked per symbol, not for the whole venue: the full exchangeInfo payload is megabytes and
            // costs far more of the venue's request weight than the one symbol a bot trades.
            document = await client.GetFromJsonAsync<JsonDocument>(
                           $"/api/v3/exchangeInfo?symbol={Uri.EscapeDataString(symbol)}",
                           cancellationToken)
                       ?? throw new InstrumentRulesUnavailableException(
                           $"{venue} returned an empty exchangeInfo body for {symbol}.");
        }
        catch (Exception exception) when (exception is not OperationCanceledException
                                             and not InstrumentRulesUnavailableException)
        {
            throw new InstrumentRulesUnavailableException(
                $"{venue} could not be asked for {symbol}'s trading rules: {exception.Message}", exception);
        }

        using (document)
        {
            if (!document.RootElement.TryGetProperty("symbols", out var symbols)
                || symbols.ValueKind != JsonValueKind.Array
                || symbols.GetArrayLength() == 0)
            {
                throw new InstrumentRulesUnavailableException(
                    $"{venue} does not list a symbol named '{symbol}'.");
            }

            return ParseBinanceSymbol(venue, symbols[0]);
        }
    }

    private InstrumentRules ParseBinanceSymbol(MarketVenue venue, JsonElement element)
    {
        var symbol = element.GetProperty("symbol").GetString()
                     ?? throw new InstrumentRulesUnavailableException($"{venue} returned a symbol with no name.");

        var status = element.TryGetProperty("status", out var statusElement) ? statusElement.GetString() : null;
        var spotAllowed = !element.TryGetProperty("isSpotTradingAllowed", out var spotElement)
                          || spotElement.ValueKind != JsonValueKind.False;

        var baseAsset = element.TryGetProperty("baseAsset", out var baseElement) ? baseElement.GetString() : null;
        var quoteAsset = element.TryGetProperty("quoteAsset", out var quoteElement) ? quoteElement.GetString() : null;

        if (string.IsNullOrWhiteSpace(baseAsset) || string.IsNullOrWhiteSpace(quoteAsset))
        {
            throw new InstrumentRulesUnavailableException(
                $"{venue} did not report base/quote assets for {symbol}; a fee and a balance cannot be " +
                "attributed to a currency this platform is guessing at.");
        }

        var supportsMarket = element.TryGetProperty("orderTypes", out var orderTypes)
                             && orderTypes.ValueKind == JsonValueKind.Array
                             && orderTypes.EnumerateArray()
                                 .Any(t => string.Equals(t.GetString(), "MARKET", StringComparison.Ordinal));

        decimal tickSize = 0m, stepSize = 0m, minQuantity = 0m, maxQuantity = 0m, minNotional = 0m;

        if (element.TryGetProperty("filters", out var filters) && filters.ValueKind == JsonValueKind.Array)
        {
            foreach (var filter in filters.EnumerateArray())
            {
                var type = filter.TryGetProperty("filterType", out var typeElement) ? typeElement.GetString() : null;

                switch (type)
                {
                    case "PRICE_FILTER":
                        tickSize = BinanceJson.DecimalOrDefault(filter, "tickSize", tickSize);
                        break;

                    case "LOT_SIZE":
                        stepSize = BinanceJson.DecimalOrDefault(filter, "stepSize", stepSize);
                        minQuantity = BinanceJson.DecimalOrDefault(filter, "minQty", minQuantity);
                        maxQuantity = BinanceJson.DecimalOrDefault(filter, "maxQty", maxQuantity);
                        break;

                    // Market orders carry their own, usually tighter, lot bounds. Take the tighter of the
                    // two on every axis; a zero here means "no market-specific bound", not "no bound".
                    case "MARKET_LOT_SIZE":
                    {
                        var marketStep = BinanceJson.DecimalOrDefault(filter, "stepSize", 0m);
                        var marketMin = BinanceJson.DecimalOrDefault(filter, "minQty", 0m);
                        var marketMax = BinanceJson.DecimalOrDefault(filter, "maxQty", 0m);

                        if (marketStep > stepSize) stepSize = marketStep;
                        if (marketMin > minQuantity) minQuantity = marketMin;
                        if (marketMax > 0m && (maxQuantity == 0m || marketMax < maxQuantity)) maxQuantity = marketMax;
                        break;
                    }

                    case "NOTIONAL":
                    case "MIN_NOTIONAL":
                    {
                        var candidate = BinanceJson.DecimalOrDefault(filter, "minNotional", 0m);
                        if (candidate > minNotional) minNotional = candidate;
                        break;
                    }
                }
            }
        }

        if (tickSize <= 0m || stepSize <= 0m)
        {
            throw new InstrumentRulesUnavailableException(
                $"{venue} reported no usable price/lot grid for {symbol} (tick {tickSize}, step {stepSize}). " +
                "Quantizing against a zero grid is not quantizing.");
        }

        var rules = new InstrumentRules(
            Symbol: symbol,
            BaseAsset: baseAsset,
            QuoteAsset: quoteAsset,
            TickSize: tickSize,
            StepSize: stepSize,
            MinQuantity: minQuantity,
            MaxQuantity: maxQuantity,
            MinNotional: minNotional,
            IsTradable: string.Equals(status, "TRADING", StringComparison.Ordinal) && spotAllowed,
            SupportsMarketOrders: supportsMarket,
            PriceScale: BinanceJson.ScaleOf(tickSize),
            QuantityScale: BinanceJson.ScaleOf(stepSize));

        logger.LogDebug(
            "Resolved {Venue} rules for {Symbol}: tick {Tick}, step {Step}, minNotional {MinNotional}, tradable {Tradable}",
            venue, symbol, tickSize, stepSize, minNotional, rules.IsTradable);

        return rules;
    }

    private sealed record CachedRules(InstrumentRules Rules, DateTimeOffset ExpiresAt);
}
