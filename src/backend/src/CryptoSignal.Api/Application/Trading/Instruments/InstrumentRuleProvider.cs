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

    /// <summary>The whole venue listing, for venues that ignore the per-symbol filter.</summary>
    private readonly ConcurrentDictionary<MarketVenue, (Dictionary<string, InstrumentRules> Rules, DateTimeOffset ExpiresAt)> fullListings = new();

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
                await FetchBinanceAsync(venue, key.Symbol, "/api/v3/exchangeInfo", cancellationToken),
            MarketVenue.BinanceFuturesTestnet =>
                await FetchBinanceAsync(venue, key.Symbol, "/fapi/v1/exchangeInfo", cancellationToken),
            MarketVenue.Bybit => await FetchBybitAsync(key.Symbol, cancellationToken),
            MarketVenue.Bitunix => await FetchBitunixAsync(venue, key.Symbol, cancellationToken),
            _ => throw new InstrumentRulesUnavailableException(
                $"No instrument-rule source is configured for venue {venue}."),
        };

        cache[key] = new CachedRules(rules, DateTimeOffset.UtcNow.Add(CacheTtl));
        return rules;
    }

    private async Task<InstrumentRules> FetchBinanceAsync(
        MarketVenue venue,
        string symbol,
        string exchangeInfoPath,
        CancellationToken cancellationToken)
    {
        var client = httpClientFactory.CreateClient(TradingHttpClients.ForVenue(venue));

        JsonDocument document;
        try
        {
            // Asked per symbol first: the full exchangeInfo payload is megabytes and costs far more of
            // the venue's request weight than the one symbol a bot trades.
            document = await client.GetFromJsonAsync<JsonDocument>(
                           $"{exchangeInfoPath}?symbol={Uri.EscapeDataString(symbol)}",
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
            if (TryFindSymbol(document.RootElement, symbol, out var entry))
                return ParseBinanceSymbol(venue, entry);

            // Some venues — Binance's futures testnet among them — ignore the `symbol` filter and answer
            // with their flagship pair. Resolving another market's grid is worse than a slow call: it
            // prices the fill and caps the quantity against the wrong instrument, and the order that
            // reaches the exchange is then sized for a market that is not the one being traded. Ask for
            // the full listing, parse it once, and keep it for the same TTL as any other cached grid.
            logger.LogInformation(
                "{Venue} answered the symbol-filtered request for {Symbol} with another market; " +
                "resolving from the full listing instead.", venue, symbol);

            return await ResolveFromFullListingAsync(venue, symbol, exchangeInfoPath, client, cancellationToken);
        }
    }

    /// <summary>
    /// Bitunix publishes its grids through the public <c>trading_pairs</c> endpoint, which ignores a
    /// per-symbol filter and always answers with the whole listing (~800 contracts). It is fetched once
    /// per TTL and indexed, which is also what makes a market-wide scanner affordable here.
    /// </summary>
    /// <remarks>
    /// Bitunix reports decimals rather than step sizes: <c>basePrecision</c> is the number of decimals a
    /// quantity may carry and <c>quotePrecision</c> the same for a price. The grid is therefore
    /// <c>10^-precision</c>, which is exact in decimal — no float rounding, unlike parsing a "0.0001" string.
    /// </remarks>
    private async Task<InstrumentRules> FetchBitunixAsync(
        MarketVenue venue, string symbol, CancellationToken cancellationToken)
    {
        if (!fullListings.TryGetValue(venue, out var listing) || listing.ExpiresAt <= DateTimeOffset.UtcNow)
        {
            var client = httpClientFactory.CreateClient(TradingHttpClients.ForVenue(venue));
            using var document = await client.GetFromJsonAsync<JsonDocument>(
                                     "/api/v1/futures/market/trading_pairs", cancellationToken)
                                 ?? throw new InstrumentRulesUnavailableException(
                                     $"{venue} returned an empty trading-pairs body.");

            if (!document.RootElement.TryGetProperty("data", out var pairs)
                || pairs.ValueKind != JsonValueKind.Array)
            {
                throw new InstrumentRulesUnavailableException($"{venue} returned no trading pairs.");
            }

            var parsed = new Dictionary<string, InstrumentRules>(StringComparer.OrdinalIgnoreCase);
            foreach (var element in pairs.EnumerateArray())
            {
                try
                {
                    var rules = ParseBitunixSymbol(venue, element);
                    parsed[rules.Symbol] = rules;
                }
                catch (InstrumentRulesUnavailableException)
                {
                    // One malformed contract must not void the listing.
                }
            }

            listing = (parsed, DateTimeOffset.UtcNow.Add(CacheTtl));
            fullListings[venue] = listing;
        }

        if (listing.Rules.TryGetValue(symbol, out var resolved))
            return resolved;

        throw new InstrumentRulesUnavailableException($"{venue} does not list a symbol named '{symbol}'.");
    }

    private InstrumentRules ParseBitunixSymbol(MarketVenue venue, JsonElement element)
    {
        var symbol = element.GetProperty("symbol").GetString()
                     ?? throw new InstrumentRulesUnavailableException($"{venue} returned a pair with no name.");
        var baseAsset = element.TryGetProperty("base", out var baseElement) ? baseElement.GetString() : null;
        var quoteAsset = element.TryGetProperty("quote", out var quoteElement) ? quoteElement.GetString() : null;

        if (string.IsNullOrWhiteSpace(baseAsset) || string.IsNullOrWhiteSpace(quoteAsset))
        {
            throw new InstrumentRulesUnavailableException(
                $"{venue} did not report base/quote assets for {symbol}.");
        }

        var status = element.TryGetProperty("symbolStatus", out var statusElement)
            ? statusElement.GetString()
            : null;
        var apiSupported = !element.TryGetProperty("isApiSupported", out var apiElement)
                           || apiElement.ValueKind != JsonValueKind.False;

        var basePrecision = element.TryGetProperty("basePrecision", out var basePrecisionElement)
                            && basePrecisionElement.TryGetInt32(out var bp) ? bp : 0;
        var quotePrecision = element.TryGetProperty("quotePrecision", out var quotePrecisionElement)
                             && quotePrecisionElement.TryGetInt32(out var qp) ? qp : 0;

        var minQuantity = BinanceJson.DecimalOrDefault(element, "minTradeVolume", 0m);
        var maxQuantity = BinanceJson.DecimalOrDefault(element, "maxMarketOrderVolume", 0m);

        return new InstrumentRules(
            Symbol: symbol,
            BaseAsset: baseAsset,
            QuoteAsset: quoteAsset,
            TickSize: Grid(quotePrecision),
            StepSize: Grid(basePrecision),
            MinQuantity: minQuantity,
            MaxQuantity: maxQuantity,
            MinNotional: 0m,
            IsTradable: string.Equals(status, "OPEN", StringComparison.OrdinalIgnoreCase) && apiSupported,
            SupportsMarketOrders: true,
            PriceScale: quotePrecision,
            QuantityScale: basePrecision);
    }

    /// <summary>The grid a decimal count implies: 4 decimals → 0.0001.</summary>
    private static decimal Grid(int decimals)
    {
        var grid = 1m;
        for (var index = 0; index < Math.Clamp(decimals, 0, 18); index++)
            grid /= 10m;
        return grid;
    }

    private async Task<InstrumentRules> ResolveFromFullListingAsync(
        MarketVenue venue,
        string symbol,
        string exchangeInfoPath,
        HttpClient client,
        CancellationToken cancellationToken)
    {
        if (!fullListings.TryGetValue(venue, out var listing) || listing.ExpiresAt <= DateTimeOffset.UtcNow)
        {
            using var document = await client.GetFromJsonAsync<JsonDocument>(exchangeInfoPath, cancellationToken)
                                 ?? throw new InstrumentRulesUnavailableException(
                                     $"{venue} returned an empty exchangeInfo listing.");
            if (!document.RootElement.TryGetProperty("symbols", out var symbols)
                || symbols.ValueKind != JsonValueKind.Array)
            {
                throw new InstrumentRulesUnavailableException($"{venue} returned no symbol listing.");
            }

            var parsed = new Dictionary<string, InstrumentRules>(StringComparer.OrdinalIgnoreCase);
            foreach (var element in symbols.EnumerateArray())
            {
                try
                {
                    var rules = ParseBinanceSymbol(venue, element);
                    parsed[rules.Symbol] = rules;
                }
                catch (InstrumentRulesUnavailableException)
                {
                    // One malformed instrument must not void the listing; the requested symbol's own
                    // lookup below will report it if it is the broken one.
                }
            }

            listing = (parsed, DateTimeOffset.UtcNow.Add(CacheTtl));
            fullListings[venue] = listing;
        }

        if (listing.Rules.TryGetValue(symbol, out var resolved))
            return resolved;

        throw new InstrumentRulesUnavailableException(
            $"{venue} does not list a symbol named '{symbol}'.");
    }

    /// <summary>Finds one symbol in an exchangeInfo body by name. Clones the element so it survives the
    /// document's disposal.</summary>
    private static bool TryFindSymbol(JsonElement root, string symbol, out JsonElement found)
    {
        found = default;
        if (!root.TryGetProperty("symbols", out var symbols) || symbols.ValueKind != JsonValueKind.Array)
            return false;

        foreach (var element in symbols.EnumerateArray())
        {
            if (element.TryGetProperty("symbol", out var name)
                && string.Equals(name.GetString(), symbol, StringComparison.OrdinalIgnoreCase))
            {
                found = element.Clone();
                return true;
            }
        }

        return false;
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

    private async Task<InstrumentRules> FetchBybitAsync(
        string symbol,
        CancellationToken cancellationToken)
    {
        var client = httpClientFactory.CreateClient(TradingHttpClients.ForVenue(MarketVenue.Bybit));
        JsonDocument document;
        try
        {
            document = await client.GetFromJsonAsync<JsonDocument>(
                           $"/v5/market/instruments-info?category=linear&symbol={Uri.EscapeDataString(symbol)}",
                           cancellationToken)
                       ?? throw new InstrumentRulesUnavailableException(
                           $"Bybit returned an empty instrument-info body for {symbol}.");
        }
        catch (Exception exception) when (exception is not OperationCanceledException
                                             and not InstrumentRulesUnavailableException)
        {
            throw new InstrumentRulesUnavailableException(
                $"Bybit could not be asked for {symbol}'s trading rules: {exception.Message}", exception);
        }

        using (document)
        {
            var root = document.RootElement;
            if (!root.TryGetProperty("retCode", out var code) || code.GetInt32() != 0)
            {
                var message = root.TryGetProperty("retMsg", out var messageElement)
                    ? messageElement.GetString()
                    : "no message";
                throw new InstrumentRulesUnavailableException(
                    $"Bybit refused instrument info for {symbol}: {message}.");
            }

            if (!root.TryGetProperty("result", out var result)
                || !result.TryGetProperty("list", out var list)
                || list.ValueKind != JsonValueKind.Array
                || list.GetArrayLength() == 0)
            {
                throw new InstrumentRulesUnavailableException($"Bybit does not list a linear symbol named '{symbol}'.");
            }

            var item = list[0];
            var status = item.TryGetProperty("status", out var statusElement) ? statusElement.GetString() : null;
            var baseAsset = item.TryGetProperty("baseCoin", out var baseElement) ? baseElement.GetString() : null;
            var quoteAsset = item.TryGetProperty("quoteCoin", out var quoteElement) ? quoteElement.GetString() : null;
            if (string.IsNullOrWhiteSpace(baseAsset) || string.IsNullOrWhiteSpace(quoteAsset))
                throw new InstrumentRulesUnavailableException($"Bybit did not report base/quote assets for {symbol}.");

            var priceFilter = item.GetProperty("priceFilter");
            var lotFilter = item.GetProperty("lotSizeFilter");
            var tickSize = DecimalProperty(priceFilter, "tickSize");
            var stepSize = DecimalProperty(lotFilter, "qtyStep");
            var minQuantity = DecimalProperty(lotFilter, "minOrderQty");
            var maxQuantity = DecimalProperty(lotFilter, "maxOrderQty");
            // Bybit linear contracts quote their minimum order in USDT under minNotionalValue;
            // some account/category responses omit it, so zero means no venue-reported minimum here,
            // not a fabricated permissive rule (the platform notional caps still apply).
            var minNotional = DecimalProperty(lotFilter, "minNotionalValue");
            if (tickSize <= 0m || stepSize <= 0m)
                throw new InstrumentRulesUnavailableException(
                    $"Bybit reported no usable price/lot grid for {symbol} (tick {tickSize}, step {stepSize}).");

            var rules = new InstrumentRules(
                Symbol: symbol,
                BaseAsset: baseAsset,
                QuoteAsset: quoteAsset,
                TickSize: tickSize,
                StepSize: stepSize,
                MinQuantity: minQuantity,
                MaxQuantity: maxQuantity,
                MinNotional: minNotional,
                IsTradable: string.Equals(status, "Trading", StringComparison.Ordinal),
                SupportsMarketOrders: true,
                PriceScale: BinanceJson.ScaleOf(tickSize),
                QuantityScale: BinanceJson.ScaleOf(stepSize));

            logger.LogDebug(
                "Resolved Bybit linear rules for {Symbol}: tick {Tick}, step {Step}, minNotional {MinNotional}, tradable {Tradable}",
                symbol, tickSize, stepSize, minNotional, rules.IsTradable);
            return rules;
        }

        static decimal DecimalProperty(JsonElement element, string property)
        {
            if (!element.TryGetProperty(property, out var value))
                return 0m;
            var text = value.ValueKind == JsonValueKind.String ? value.GetString() : value.ToString();
            return decimal.TryParse(text, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out var parsed) ? parsed : 0m;
        }
    }

    private sealed record CachedRules(InstrumentRules Rules, DateTimeOffset ExpiresAt);
}
