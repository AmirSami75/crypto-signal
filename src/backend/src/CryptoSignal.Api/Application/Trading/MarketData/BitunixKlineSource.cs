using System.Globalization;
using System.Text.Json;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Extensions.Type;

namespace CryptoSignal.Api.Application.Trading.MarketData;

/// <summary>
/// Reads closed candles from Bitunix's public futures market API.
/// </summary>
/// <remarks>
/// <para>
/// Bitunix's OpenAPI is futures-only and its kline payload differs enough from Binance's that this is
/// a sibling of <c>BinanceKlineSource</c>, not a subclass: candles arrive as JSON objects with string
/// prices under <c>data</c>, the open-time field is <c>time</c> in Unix milliseconds, and there is no
/// close-time field — it is derived by adding one interval, exactly as Binance's own close time would
/// be computed.
/// </para>
/// <para>
/// The same two rules as every other source hold: the forming candle is dropped by timestamp rather
/// than by index, and a short window faults rather than being padded or fetched from another venue.
/// </para>
/// </remarks>
public sealed class BitunixKlineSource(IHttpClientFactory httpClientFactory, ILogger<BitunixKlineSource> logger)
    : IMarketDataSource, IScopedSvcMarker
{
    // Measured at the venue: asking for 300 returns exactly 200.
    private const int VenueMaxLimit = 200;
    private const int FormingCandleAllowance = 2;

    public MarketVenue Venue => MarketVenue.Bitunix;

    public async Task<IReadOnlyList<MarketCandleData>> GetClosedCandlesAsync(
        string symbol,
        string interval,
        int count,
        CancellationToken cancellationToken)
    {
        if (count <= 0)
            throw new ArgumentOutOfRangeException(nameof(count), count, "A positive candle count is required.");

        // Bitunix caps a single request well below what a bot window needs, so this source pages
        // backward: each page asks for everything up to the oldest open time seen so far. The page
        // size leaves room for the forming-candle allowance without ever exceeding the cap.
        var pageSize = Math.Min(VenueMaxLimit, count + FormingCandleAllowance);
        var pagesNeeded = (int)Math.Ceiling((double)count / (VenueMaxLimit - FormingCandleAllowance));

        var duration = CandleInterval.ToTimeSpan(interval);
        var normalizedSymbol = symbol.Trim().ToUpperInvariant();
        var client = httpClientFactory.CreateClient(TradingHttpClients.ForVenue(Venue));

        // Bitunix's interval tokens are the familiar Binance-style ones ("1m".."1w") for the intervals
        // the engine models. Anything else is refused here rather than sent to be misread.
        var bitunixInterval = NormalizeInterval(interval);

        var now = DateTimeOffset.UtcNow;
        var closed = new List<MarketCandleData>(count + FormingCandleAllowance);
        long? endTime = null;

        while (closed.Count < count && pagesNeeded > 0)
        {
            pagesNeeded--;

            var url = $"/api/v1/futures/market/kline?symbol={Uri.EscapeDataString(normalizedSymbol)}" +
                      $"&interval={Uri.EscapeDataString(bitunixInterval)}&limit={pageSize}";
            if (endTime is { } until)
                url += $"&endTime={until.ToString(CultureInfo.InvariantCulture)}";

            BitunixEnvelope<JsonElement>? envelope;
            try
            {
                envelope = await client.GetFromJsonAsync<BitunixEnvelope<JsonElement>>(url, cancellationToken);
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                throw new HttpRequestException(
                    $"Bitunix could not be asked for {normalizedSymbol} {interval} klines: {exception.Message}",
                    exception);
            }

            if (envelope is null || envelope.Code != 0)
            {
                throw new InvalidDataException(
                    $"Bitunix refused the kline request for {normalizedSymbol}: code {envelope?.Code}, " +
                    $"{envelope?.Msg ?? "no message"}.");
            }

            var pageClosed = 0;
            foreach (var kline in envelope.Data.EnumerateArray())
            {
                var candle = ParseKline(kline, normalizedSymbol, duration);

                // Same rule as the Binance source: drop the forming candle by its own timestamps,
                // never by position, because the venue does not promise whether it is present.
                if (candle.CloseTime > now)
                    continue;

                closed.Add(candle);
                pageClosed++;

                if (endTime is null || candle.OpenTime.ToUnixTimeMilliseconds() < endTime)
                    endTime = candle.OpenTime.ToUnixTimeMilliseconds();
            }

            // A short page with no closed candles means the venue has nothing older to offer; paging on
            // would loop forever against a hard wall.
            if (pageClosed == 0)
                break;
        }

        if (closed.Count < count)
        {
            throw new InvalidDataException(
                $"Bitunix returned {closed.Count} closed candles for {normalizedSymbol} {interval} but " +
                $"{count} were requested. The window is not padded and no other venue is asked.");
        }

        closed.Sort((a, b) => a.OpenTime.CompareTo(b.OpenTime));
        var window = closed.GetRange(closed.Count - count, count);

        AssertContiguous(window, duration, normalizedSymbol, interval);

        logger.LogDebug(
            "Bitunix served {Count} closed candles for {Symbol} {Interval}, newest opening {OpenTime:o}",
            window.Count, normalizedSymbol, interval, window[^1].OpenTime);

        return window;
    }

    private static string NormalizeInterval(string interval) => interval.Trim() switch
    {
        "1m" or "3m" or "5m" or "15m" or "30m" or "1h" or "2h" or "4h" or "6h" or "12h" or "1d" => interval.Trim(),
        _ => throw new NotSupportedException(
            $"Bitunix has no kline interval '{interval}'. Supported: 1m..12h, 1d."),
    };

    private static MarketCandleData ParseKline(JsonElement kline, string symbol, TimeSpan duration)
    {
        decimal Decimal(string name) =>
            decimal.Parse(
                kline.GetProperty(name).GetString()
                ?? throw new InvalidDataException($"Bitunix kline for {symbol} has a null {name}."),
                CultureInfo.InvariantCulture);

        // Bitunix sends the open time as a stringified epoch-millisecond value ("1787648400000").
        var openMs = long.Parse(
            kline.GetProperty("time").GetString()
            ?? throw new InvalidDataException($"Bitunix kline for {symbol} has a null time."),
            CultureInfo.InvariantCulture);
        var openTime = DateTimeOffset.FromUnixTimeMilliseconds(openMs);

        return new MarketCandleData(
            OpenTime: openTime,
            CloseTime: openTime + duration,
            Open: Decimal("open"),
            High: Decimal("high"),
            Low: Decimal("low"),
            Close: Decimal("close"),
            Volume: Decimal("baseVol"),
            QuoteVolume: Decimal("quoteVol"));
    }

    private static void AssertContiguous(
        IReadOnlyList<MarketCandleData> window, TimeSpan duration, string symbol, string interval)
    {
        for (var i = 1; i < window.Count; i++)
        {
            if (window[i].OpenTime - window[i - 1].OpenTime != duration)
            {
                throw new InvalidDataException(
                    $"Bitunix returned a gap in the {symbol} {interval} window between " +
                    $"{window[i - 1].OpenTime:o} and {window[i].OpenTime:o}. A gapped window would feed the " +
                    "model candles that are not neighbours; it faults instead.");
            }
        }
    }
}

/// <summary>The uniform Bitunix response wrapper: code 0 means success.</summary>
public sealed record BitunixEnvelope<T>(int Code, T Data, string? Msg);
