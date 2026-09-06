using System.Globalization;
using System.Net.Http.Json;
using System.Text.Json;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;

namespace CryptoSignal.Api.Application.Trading.MarketData;

/// <summary>
/// Reads the Binance <c>/fapi/v1/ticker/24hr</c> endpoint — 24-hour price change,
/// volume, and ATR for every USDT-margined futures symbol. Used by the market
/// scanner to rank symbols by (|change| × log10(volume)).
/// </summary>
public interface IBinanceFuturesTickerSource
{
    /// <summary>All 24h tickers, ranked descending by the scan score.</summary>
    Task<IReadOnlyList<ScannerTicker>> GetTickersAsync(CancellationToken cancellationToken);
}

/// <summary>One symbol's 24-hour ticker summary, as the scanner consumes it.</summary>
public sealed record ScannerTicker(
    string Symbol,
    decimal PriceChangePercent,
    decimal QuoteVolume,
    decimal WeightedAvgPrice,
    decimal LastPrice,
    decimal HighPrice,
    decimal LowPrice);

/// <summary>
/// Fetches 24h tickers from the Binance Futures Testnet <c>/fapi/v1/ticker/24hr</c> endpoint.
/// </summary>
/// <remarks>
/// The endpoint is unauthenticated and subject to a 40-weight-per-minute limit
/// (docs/ARCHITECTURE.md §rate-limits). The scanner caps the number of symbols
/// it processes per pass to stay within that budget.
/// </remarks>
public sealed class BinanceFuturesTickerSource(
    IHttpClientFactory httpClientFactory,
    ILogger<BinanceFuturesTickerSource> logger)
    : IBinanceFuturesTickerSource, IScopedSvcMarker
{
    /// <summary>The Binance Futures 24h ticker endpoint.</summary>
    private const string TickersPath = "/fapi/v1/ticker/24hr";

    /// <summary>Cap the number of tickers returned — the scanner ranks, not enumerates.</summary>
    private const int MaxTickers = 500;

    public MarketVenue Venue => MarketVenue.BinanceFuturesTestnet;

    public async Task<IReadOnlyList<ScannerTicker>> GetTickersAsync(CancellationToken cancellationToken)
    {
        var client = httpClientFactory.CreateClient(TradingHttpClients.BinanceFuturesTestnet);
        var url = TickersPath;

        JsonDocument document;
        try
        {
            document = await client.GetFromJsonAsync<JsonDocument>(url, cancellationToken)
                       ?? throw new InvalidDataException($"{Venue} returned an empty tickers body.");
        }
        catch (Exception exception) when (exception is not OperationCanceledException and not InvalidDataException)
        {
            throw new HttpRequestException(
                $"{Venue} could not be asked for 24h tickers: {exception.Message}",
                exception);
        }

        using (document)
        {
            if (document.RootElement.ValueKind != JsonValueKind.Array)
            {
                throw new InvalidDataException(
                    $"{Venue} answered the tickers request with {document.RootElement.ValueKind}, not an array.");
            }

            var tickers = new List<ScannerTicker>(MaxTickers);
            foreach (var ticker in document.RootElement.EnumerateArray())
            {
                if (tickers.Count >= MaxTickers)
                    break;

                // Binance returns prices as strings; parse with invariant culture.
                tickers.Add(new ScannerTicker(
                    Symbol: ticker.GetProperty("symbol").GetString() ?? string.Empty,
                    PriceChangePercent: BinanceJson.Decimal(ticker.GetProperty("priceChangePercent"), "priceChangePercent"),
                    QuoteVolume: BinanceJson.Decimal(ticker.GetProperty("quoteVolume"), "quoteVolume"),
                    WeightedAvgPrice: BinanceJson.Decimal(ticker.GetProperty("weightedAvgPrice"), "weightedAvgPrice"),
                    LastPrice: BinanceJson.Decimal(ticker.GetProperty("lastPrice"), "lastPrice"),
                    HighPrice: BinanceJson.Decimal(ticker.GetProperty("highPrice"), "highPrice"),
                    LowPrice: BinanceJson.Decimal(ticker.GetProperty("lowPrice"), "lowPrice")
                ));
            }

            // Score = |change%| × log10(quoteVolume); rank descending.
            var ranked = tickers
                .Where(t => t.Symbol.EndsWith("USDT", StringComparison.Ordinal))
                .OrderByDescending(t =>
                    Math.Abs((double)t.PriceChangePercent) *
                    Math.Log10(Math.Max(1.0, (double)t.QuoteVolume)))
                .ToList();

            logger.LogDebug(
                "{Venue} served {Count} tickers, ranked {Ranked} tradable USDT symbols",
                Venue, tickers.Count, ranked.Count);

            return ranked;
        }
    }
}
