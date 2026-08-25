using System.Net.Http.Json;
using System.Text.Json;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.MarketData;

/// <summary>
/// Closed candles from a Binance-compatible <c>/api/v3/klines</c> endpoint. Shared by the testnet and
/// mainnet sources, which differ only in which host they address.
/// </summary>
/// <remarks>
/// <para>
/// <b>The venue's last kline is the candle still forming, and it is always discarded.</b> Its high, low and
/// close move for the rest of the interval, so a feature computed from it encodes information the model
/// will not have at decision time in production — the textbook look-ahead leak. The request therefore asks
/// for two extra klines and keeps only those whose close time is already in the past.
/// </para>
/// <para>
/// <b>A gap in the window throws.</b> Consecutive open times must be exactly one interval apart; a hole
/// means the venue is missing candles, and every lookback feature computed across it silently spans more
/// wall-clock time than it claims. Faulting the bot is the required behaviour — the safety policy names
/// treating missing data as permission to trade as the antipattern to avoid, and there is no fallback venue
/// to ask.
/// </para>
/// </remarks>
public abstract class BinanceKlineSource(IHttpClientFactory httpClientFactory, ILogger logger)
    : IMarketDataSource
{
    /// <summary>The venue's own hard ceiling on klines per request.</summary>
    private const int VenueMaxLimit = 1000;

    /// <summary>How many extra klines to ask for, to cover the forming candle and one boundary race.</summary>
    private const int FormingCandleAllowance = 2;

    public abstract MarketVenue Venue { get; }

    public async Task<IReadOnlyList<MarketCandleData>> GetClosedCandlesAsync(
        string symbol,
        string interval,
        int count,
        CancellationToken cancellationToken)
    {
        if (count <= 0)
            throw new ArgumentOutOfRangeException(nameof(count), count, "A positive candle count is required.");

        var requested = count + FormingCandleAllowance;
        if (requested > VenueMaxLimit)
        {
            throw new ArgumentOutOfRangeException(
                nameof(count), count,
                $"{Venue} serves at most {VenueMaxLimit} klines per request, and {FormingCandleAllowance} of " +
                "those are spent covering the forming candle. Paging is not implemented because no bot window " +
                "needs it; asking for more would silently return fewer.");
        }

        var duration = CandleInterval.ToTimeSpan(interval);
        var normalizedSymbol = symbol.Trim().ToUpperInvariant();
        var client = httpClientFactory.CreateClient(TradingHttpClients.ForVenue(Venue));

        var url = $"/api/v3/klines?symbol={Uri.EscapeDataString(normalizedSymbol)}" +
                  $"&interval={Uri.EscapeDataString(interval.Trim())}&limit={requested}";

        JsonDocument document;
        try
        {
            document = await client.GetFromJsonAsync<JsonDocument>(url, cancellationToken)
                       ?? throw new InvalidDataException($"{Venue} returned an empty klines body for {normalizedSymbol}.");
        }
        catch (Exception exception) when (exception is not OperationCanceledException and not InvalidDataException)
        {
            // Rethrown as-is for the tick handler to turn into a fault. Explicitly not caught-and-defaulted:
            // an unreachable venue must stop the bot, not hand it an empty window.
            throw new HttpRequestException(
                $"{Venue} could not be asked for {normalizedSymbol} {interval} klines: {exception.Message}",
                exception);
        }

        using (document)
        {
            if (document.RootElement.ValueKind != JsonValueKind.Array)
            {
                throw new InvalidDataException(
                    $"{Venue} answered the klines request for {normalizedSymbol} with " +
                    $"{document.RootElement.ValueKind}, not an array.");
            }

            var now = DateTimeOffset.UtcNow;
            var closed = new List<MarketCandleData>(requested);

            foreach (var kline in document.RootElement.EnumerateArray())
            {
                var candle = ParseKline(kline, normalizedSymbol);

                // The forming candle, and anything ahead of it, is dropped here rather than trimmed by index:
                // the venue does not promise the forming candle is present (a request landing exactly on a
                // boundary may return only closed ones), so counting back from the end would drop a real one.
                if (candle.CloseTime <= now)
                    closed.Add(candle);
            }

            if (closed.Count < count)
            {
                throw new InvalidDataException(
                    $"{Venue} returned {closed.Count} closed candles for {normalizedSymbol} {interval} but " +
                    $"{count} were requested. The window is not padded and no other venue is asked.");
            }

            closed.Sort((a, b) => a.OpenTime.CompareTo(b.OpenTime));
            var window = closed.GetRange(closed.Count - count, count);

            AssertContiguous(window, duration, normalizedSymbol, interval);

            logger.LogDebug(
                "{Venue} served {Count} closed candles for {Symbol} {Interval}, newest opening {OpenTime:o}",
                Venue, window.Count, normalizedSymbol, interval, window[^1].OpenTime);

            return window;
        }
    }

    private MarketCandleData ParseKline(JsonElement kline, string symbol)
    {
        // [ openTime, open, high, low, close, volume, closeTime, quoteVolume, tradeCount, ... ]
        if (kline.ValueKind != JsonValueKind.Array || kline.GetArrayLength() < 7)
        {
            throw new InvalidDataException(
                $"{Venue} returned a kline for {symbol} with {(kline.ValueKind == JsonValueKind.Array ? kline.GetArrayLength() : 0)} " +
                "fields; at least 7 are required.");
        }

        return new MarketCandleData(
            OpenTime: BinanceJson.Timestamp(kline[0], "openTime"),
            CloseTime: BinanceJson.Timestamp(kline[6], "closeTime"),
            Open: BinanceJson.Decimal(kline[1], "open"),
            High: BinanceJson.Decimal(kline[2], "high"),
            Low: BinanceJson.Decimal(kline[3], "low"),
            Close: BinanceJson.Decimal(kline[4], "close"),
            Volume: BinanceJson.Decimal(kline[5], "volume"),
            QuoteVolume: kline.GetArrayLength() > 7 ? BinanceJson.Decimal(kline[7], "quoteVolume") : null,
            TradeCount: kline.GetArrayLength() > 8 ? BinanceJson.IntOrNull(kline[8]) : null);
    }

    private void AssertContiguous(
        IReadOnlyList<MarketCandleData> window,
        TimeSpan duration,
        string symbol,
        string interval)
    {
        for (var i = 1; i < window.Count; i++)
        {
            var gap = window[i].OpenTime - window[i - 1].OpenTime;
            if (gap == duration)
                continue;

            throw new InvalidDataException(
                $"{Venue}'s {symbol} {interval} window is not contiguous: {window[i - 1].OpenTime:o} is " +
                $"followed by {window[i].OpenTime:o}, a {gap} step where {duration} was expected. A window " +
                "with a hole makes every lookback feature span more time than it reports.");
        }
    }
}

/// <summary>Klines from the Binance spot testnet — the only venue reachable from inside the containers.</summary>
/// <remarks>
/// The same venue the sandbox broker fills against, deliberately: candles and fills come from one price
/// source, so a paper or sandbox decision can be checked against the prices that produced it.
/// </remarks>
public sealed class BinanceTestnetKlineSource(
    IHttpClientFactory httpClientFactory,
    ILogger<BinanceTestnetKlineSource> logger)
    : BinanceKlineSource(httpClientFactory, logger), IScopedSvcMarker
{
    public override MarketVenue Venue => MarketVenue.BinanceTestnet;
}

/// <summary>
/// Klines from Binance production. Registered but unreachable from the containers today; it needs egress or
/// a configured proxy.
/// </summary>
/// <remarks>
/// Registered anyway so selecting it is a configuration change rather than a code change — and so the
/// failure, when egress is missing, is a loud fault naming this venue rather than a silent switch to the
/// testnet's prices.
/// </remarks>
public sealed class BinanceMainnetKlineSource(
    IHttpClientFactory httpClientFactory,
    ILogger<BinanceMainnetKlineSource> logger)
    : BinanceKlineSource(httpClientFactory, logger), IScopedSvcMarker
{
    public override MarketVenue Venue => MarketVenue.BinanceMainnet;
}
