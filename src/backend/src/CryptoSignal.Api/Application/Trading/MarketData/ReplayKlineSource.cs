using System.Globalization;
using Microsoft.Extensions.Options;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.MarketData;

/// <summary>
/// Serves closed candles from the recorded <c>&lt;SYMBOL&gt;_&lt;interval&gt;.csv</c> files — deterministic,
/// for tests and backfills.
/// </summary>
/// <remarks>
/// <para>
/// Every file is a snapshot of already-closed candles, so there is no "in-progress" candle to drop and
/// the newest row is the newest closed candle by construction. The source returns the last
/// <c>count</c> rows, oldest first, exactly as a live source would.
/// </para>
/// <para>
/// The no-fallback rule is absolute here too: a missing file, an unreadable row, or fewer than
/// <c>count</c> rows all throw. A replay that quietly padded a short history would let a
/// backtest run on a window the model was never given, which is the same lie as substituting a venue.
/// </para>
/// </remarks>
public sealed class ReplayKlineSource(
    IOptions<MarketDataOptions> options,
    ILogger<ReplayKlineSource> logger) : IMarketDataSource, IScopedSvcMarker
{
    public MarketVenue Venue => MarketVenue.Replay;

    public async Task<IReadOnlyList<MarketCandleData>> GetClosedCandlesAsync(
        string symbol,
        string interval,
        int count,
        CancellationToken cancellationToken)
    {
        if (count <= 0)
            throw new ArgumentOutOfRangeException(nameof(count), count, "A positive candle count is required.");

        var directory = options.Value.ReplayDataDirectory;
        if (string.IsNullOrWhiteSpace(directory))
        {
            throw new InvalidOperationException(
                "MarketData:ReplayDataDirectory is not set, so the replay source has no data to read. It is " +
                "left empty on purpose — a guessed directory reads the wrong fixture silently.");
        }

        var fileName = $"{symbol.Trim().ToUpperInvariant()}_{interval.Trim()}.csv";
        var path = Path.Combine(directory, fileName);

        if (!File.Exists(path))
        {
            throw new FileNotFoundException(
                $"The replay source has no recording for {symbol} {interval} (looked for {fileName}). " +
                "It will not substitute another symbol's or interval's candles.", path);
        }

        var duration = CandleInterval.ToTimeSpan(interval);
        var candles = new List<MarketCandleData>();

        // Streamed, not ReadAllLines: the recordings run to tens of thousands of rows and only the tail is
        // wanted. Parsing the whole file keeps the reader simple and the files are local, so the cost is
        // acceptable; the alternative — seeking from the end — would have to re-find row boundaries anyway.
        using (var reader = new StreamReader(path))
        {
            var header = await reader.ReadLineAsync(cancellationToken);
            if (header is null)
                throw new InvalidDataException($"The replay file {fileName} is empty.");

            string? line;
            var lineNumber = 1;
            while ((line = await reader.ReadLineAsync(cancellationToken)) is not null)
            {
                lineNumber++;
                if (line.Length == 0)
                    continue;

                candles.Add(ParseRow(line, fileName, lineNumber, duration));
            }
        }

        if (candles.Count < count)
        {
            throw new InvalidDataException(
                $"The replay file {fileName} holds {candles.Count} candles but {count} were requested. " +
                "The replay source will not pad a short window.");
        }

        // Recordings are written oldest-first, but do not trust that — sort, then take the newest slice.
        candles.Sort((a, b) => a.OpenTime.CompareTo(b.OpenTime));
        var window = candles.GetRange(candles.Count - count, count);

        logger.LogDebug("Replay served {Count} candles for {Symbol} {Interval} from {File}",
            window.Count, symbol, interval, fileName);

        return window;
    }

    private static MarketCandleData ParseRow(string line, string fileName, int lineNumber, TimeSpan duration)
    {
        // timestamp,open,high,low,close,volume,close_time,quote_volume,trade_count,taker_buy_base_volume,taker_buy_quote_volume
        var fields = line.Split(',');
        if (fields.Length < 6)
        {
            throw new InvalidDataException(
                $"{fileName} line {lineNumber} has {fields.Length} columns; at least 6 are required.");
        }

        var openTime = ParseTimestamp(fields[0], fileName, lineNumber);

        // The recording's own close time is preferred over openTime + duration: it is what the venue said,
        // and an audit that compares a replayed candle to the live one should see the venue's value.
        var closeTime = fields.Length > 6 && DateTimeOffset.TryParse(
            fields[6], CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var recorded)
            ? recorded
            : openTime + duration;

        return new MarketCandleData(
            OpenTime: openTime,
            CloseTime: closeTime,
            Open: Money(fields[1], fileName, lineNumber, "open"),
            High: Money(fields[2], fileName, lineNumber, "high"),
            Low: Money(fields[3], fileName, lineNumber, "low"),
            Close: Money(fields[4], fileName, lineNumber, "close"),
            Volume: Money(fields[5], fileName, lineNumber, "volume"),
            QuoteVolume: fields.Length > 7 ? MoneyOrNull(fields[7]) : null,
            TradeCount: fields.Length > 8 ? IntOrNull(fields[8]) : null);
    }

    private static DateTimeOffset ParseTimestamp(string value, string fileName, int lineNumber)
    {
        // Recorded as "2020-01-01 00:00:00+00:00". Invariant + assume-UTC so a machine in a Persian locale
        // reads the same instant a UTC one does.
        if (DateTimeOffset.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                out var parsed))
        {
            return parsed;
        }

        throw new InvalidDataException($"{fileName} line {lineNumber} has an unparseable timestamp '{value}'.");
    }

    private static decimal Money(string value, string fileName, int lineNumber, string field)
    {
        if (decimal.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed))
            return parsed;

        throw new InvalidDataException(
            $"{fileName} line {lineNumber} has a non-decimal {field} value '{value}'.");
    }

    private static decimal? MoneyOrNull(string value) =>
        decimal.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed) ? parsed : null;

    private static int? IntOrNull(string value) =>
        int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed) ? parsed : null;
}
