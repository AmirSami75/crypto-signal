using System.Globalization;

namespace CryptoSignal.Api.Application.Trading.Models;

/// <summary>
/// Converts an exchange interval token (<c>1m</c>, <c>15m</c>, <c>1h</c>, <c>4h</c>, <c>1d</c>,
/// <c>1w</c>) into a duration.
/// </summary>
/// <remarks>
/// <para>
/// Parsing is strict and total: an unrecognised token throws rather than resolving to a default. The
/// duration decides how stale a candle window is allowed to be and when a signal expires, so a token
/// silently read as one minute would make a daily bot's freshness check permanently fail, and a token
/// read as one day would make a one-minute bot act on hour-old prices.
/// </para>
/// <para>
/// Months are not supported. Binance spells them <c>1M</c> — a single case flip away from <c>1m</c>,
/// which is a 43,200× difference in duration. A platform that never needs monthly candles should not
/// carry that trap.
/// </para>
/// </remarks>
public static class CandleInterval
{
    /// <summary>The duration of one candle, or throws when the token is not one this platform accepts.</summary>
    public static TimeSpan ToTimeSpan(string interval)
    {
        if (TryToTimeSpan(interval, out var duration))
            return duration;

        throw new ArgumentException(
            $"'{interval}' is not a supported candle interval. Use minutes (1m, 3m, 5m, 15m, 30m), " +
            "hours (1h, 2h, 4h, 6h, 8h, 12h), days (1d, 3d) or weeks (1w).",
            nameof(interval));
    }

    public static bool TryToTimeSpan(string? interval, out TimeSpan duration)
    {
        duration = TimeSpan.Zero;

        if (string.IsNullOrWhiteSpace(interval) || interval.Length < 2)
            return false;

        var token = interval.Trim();
        var unit = token[^1];
        var digits = token[..^1];

        // Case-sensitive on purpose: 'M' (month) is not accepted, and must not fall through to 'm'.
        if (!int.TryParse(digits, NumberStyles.None, CultureInfo.InvariantCulture, out var count) || count <= 0)
            return false;

        duration = unit switch
        {
            'm' => TimeSpan.FromMinutes(count),
            'h' => TimeSpan.FromHours(count),
            'd' => TimeSpan.FromDays(count),
            'w' => TimeSpan.FromDays(7 * count),
            _ => TimeSpan.Zero,
        };

        return duration > TimeSpan.Zero;
    }
}
