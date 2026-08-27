using System.Globalization;
using System.Text.Json;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.MarketData;

/// <summary>
/// Reads closed candles from Bybit's v5 public market API (demo host).
/// </summary>
/// <remarks>
/// <para>
/// Bybit v5 klines arrive as a <c>list</c> of 7-tuples — <c>[start, open, high, low, close, volume,
/// turnover]</c> — with string values, under <c>result</c>, newest first. There is no close-time field;
/// it is derived by adding one interval, exactly as the other sources do.
/// </para>
/// <para>
/// The same two rules as every source hold: the forming candle is dropped by timestamp rather than by
/// index, and a short window faults rather than being padded or fetched from another venue.
/// </para>
/// </remarks>
public sealed class BybitKlineSource(IHttpClientFactory httpClientFactory, ILogger<BybitKlineSource> logger)
    : IMarketDataSource, IScopedSvcMarker
{
    // Bybit v5 caps a kline request at 1000 candles — well above any bot window, so no paging.
    private const int VenueMaxLimit = 1000;
    private const int FormingCandleAllowance = 2;

    public MarketVenue Venue => MarketVenue.Bybit;

    public async Task<IReadOnlyList<MarketCandleData>> GetClosedCandlesAsync(
        string symbol,
        string interval,
        int count,
        CancellationToken cancellationToken)
    {
        if (count <= 0)
            throw new ArgumentOutOfRangeException(nameof(count), count, "A positive candle count is required.");

        var limit = Math.Min(VenueMaxLimit, count + FormingCandleAllowance);
        var duration = CandleInterval.ToTimeSpan(interval);
        var normalizedSymbol = symbol.Trim().ToUpperInvariant();
        var bybitInterval = NormalizeInterval(interval);
        var client = httpClientFactory.CreateClient(TradingHttpClients.ForVenue(Venue));
        var now = DateTimeOffset.UtcNow;

        var url = $"/v5/market/kline?category=linear&symbol={Uri.EscapeDataString(normalizedSymbol)}" +
                  $"&interval={Uri.EscapeDataString(bybitInterval)}&limit={limit}";

        BybitResult<BybitKlineResult>? response;
        try
        {
            response = await client.GetFromJsonAsync<BybitResult<BybitKlineResult>>(url, cancellationToken);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            throw new HttpRequestException(
                $"Bybit could not be asked for {normalizedSymbol} {interval} klines: {exception.Message}",
                exception);
        }

        if (response is null || response.RetCode != 0)
            throw new InvalidDataException(
                $"Bybit refused the kline request for {normalizedSymbol}: retCode {response?.RetCode}, " +
                $"{response?.RetMsg ?? "no message"}.");

        var closed = new List<MarketCandleData>(count);
        foreach (var row in response.Result?.List ?? [])
        {
            var candle = ParseKline(row, normalizedSymbol, duration);
            // Drop the forming candle by its own timestamps, never by index.
            if (candle.CloseTime > now)
                continue;
            closed.Add(candle);
        }

        if (closed.Count < count)
            throw new InvalidDataException(
                $"Bybit returned {closed.Count} closed candles for {normalizedSymbol} {interval} but " +
                $"{count} were requested. The window is not padded and no other venue is asked.");

        // Newest-first on the wire; the interface promises oldest-first.
        closed.Sort((a, b) => a.OpenTime.CompareTo(b.OpenTime));
        var window = closed.GetRange(closed.Count - count, count);

        AssertContiguous(window, duration, normalizedSymbol, interval);

        logger.LogDebug(
            "Bybit served {Count} closed candles for {Symbol} {Interval}, newest opening {OpenTime:o}",
            window.Count, normalizedSymbol, interval, window[^1].OpenTime);

        return window;
    }

    /// <summary>Bybit's v5 interval tokens are minute-counts and letters, not Binance-style suffixes.</summary>
    private static string NormalizeInterval(string interval) => interval.Trim() switch
    {
        "1m" => "1",
        "3m" => "3",
        "5m" => "5",
        "15m" => "15",
        "30m" => "30",
        "1h" => "60",
        "2h" => "120",
        "4h" => "240",
        "6h" => "360",
        "12h" => "720",
        "1d" => "D",
        _ => throw new NotSupportedException(
            $"Bybit has no kline interval '{interval}'. Supported: 1m..12h, 1d."),
    };

    private static MarketCandleData ParseKline(JsonElement row, string symbol, TimeSpan duration)
    {
        decimal Dec(int index) =>
            decimal.Parse(
                row[index].GetString()
                ?? throw new InvalidDataException($"Bybit kline for {symbol} has a null value at index {index}."),
                CultureInfo.InvariantCulture);

        // row[0] is the open time in Unix milliseconds (stringified).
        var openMs = long.Parse(
            row[0].GetString()
            ?? throw new InvalidDataException($"Bybit kline for {symbol} has a null open time."),
            CultureInfo.InvariantCulture);
        var openTime = DateTimeOffset.FromUnixTimeMilliseconds(openMs);

        var open = Dec(1);
        var high = Dec(2);
        var low = Dec(3);
        var close = Dec(4);
        var volume = Dec(5);   // base-asset volume
        var turnover = Dec(6); // quote-asset turnover

        // Same sanitizer as the other futures source: a venue occasionally emits candles whose own
        // fields violate OHLC bounds. Widen to cover, never shrink a real extreme.
        high = Math.Max(high, Math.Max(open, close));
        low = Math.Min(low, Math.Min(open, close));

        return new MarketCandleData(
            OpenTime: openTime,
            CloseTime: openTime + duration,
            Open: open,
            High: high,
            Low: low,
            Close: close,
            Volume: volume,
            QuoteVolume: turnover);
    }

    private static void AssertContiguous(
        IReadOnlyList<MarketCandleData> window, TimeSpan duration, string symbol, string interval)
    {
        for (var i = 1; i < window.Count; i++)
        {
            if (window[i].OpenTime - window[i - 1].OpenTime != duration)
            {
                throw new InvalidDataException(
                    $"Bybit returned a gap in the {symbol} {interval} window between " +
                    $"{window[i - 1].OpenTime:o} and {window[i].OpenTime:o}. A gapped window would feed the " +
                    "model candles that are not neighbours; it faults instead.");
            }
        }
    }
}

/// <summary>Bybit v5 uniform response wrapper: retCode 0 means success.</summary>
public sealed record BybitResult<T>(int RetCode, string? RetMsg, T? Result);

/// <summary>The <c>result</c> object of a kline response.</summary>
public sealed record BybitKlineResult(string Symbol, string Category, IReadOnlyList<JsonElement> List);
