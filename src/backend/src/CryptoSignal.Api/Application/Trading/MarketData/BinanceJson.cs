using System.Globalization;
using System.Text.Json;

namespace CryptoSignal.Api.Application.Trading.MarketData;

/// <summary>
/// Reads Binance's JSON, where every price and quantity arrives as a <em>string</em>.
/// </summary>
/// <remarks>
/// <para>
/// Invariant culture on every parse, without exception. This application runs in a Persian locale, and a
/// culture-sensitive parse of <c>"0.01"</c> would read one hundredth as one — a tick size wrong by two
/// orders of magnitude, which quantizes an order onto a grid the venue does not have.
/// </para>
/// <para>
/// Every helper throws on malformed input rather than yielding zero. A zero tick size disables
/// quantization, a zero minimum notional disables the smallest-order check, and a zero price becomes an
/// entry price of zero on a stored intent — each is a valid <see cref="decimal"/> and a silent failure.
/// </para>
/// </remarks>
internal static class BinanceJson
{
    /// <summary>A decimal from a JSON string (or number), or throws naming the field.</summary>
    public static decimal Decimal(JsonElement element, string field)
    {
        var raw = element.ValueKind switch
        {
            JsonValueKind.String => element.GetString(),
            JsonValueKind.Number => element.GetRawText(),
            _ => null,
        };

        if (raw is null || !decimal.TryParse(
                raw,
                NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint | NumberStyles.AllowExponent,
                CultureInfo.InvariantCulture,
                out var parsed))
        {
            throw new FormatException($"Binance returned '{raw ?? element.ValueKind.ToString()}' for {field}, which is not a decimal number.");
        }

        return parsed;
    }

    /// <summary>A decimal from an optional field, or <paramref name="fallback"/> when it is absent.</summary>
    public static decimal DecimalOrDefault(JsonElement parent, string property, decimal fallback) =>
        parent.TryGetProperty(property, out var element) && element.ValueKind is not JsonValueKind.Null
            ? Decimal(element, property)
            : fallback;

    /// <summary>Epoch milliseconds from a JSON number (or string), or throws naming the field.</summary>
    public static DateTimeOffset Timestamp(JsonElement element, string field)
    {
        long milliseconds;

        if (element.ValueKind is JsonValueKind.Number && element.TryGetInt64(out var number))
        {
            milliseconds = number;
        }
        else if (element.ValueKind is JsonValueKind.String
                 && long.TryParse(element.GetString(), NumberStyles.None, CultureInfo.InvariantCulture, out var text))
        {
            milliseconds = text;
        }
        else
        {
            throw new FormatException($"Binance returned a non-timestamp for {field}.");
        }

        return DateTimeOffset.FromUnixTimeMilliseconds(milliseconds);
    }

    /// <summary>An int from a JSON number, or null when the venue did not report one.</summary>
    public static int? IntOrNull(JsonElement element) =>
        element.ValueKind is JsonValueKind.Number && element.TryGetInt32(out var value) ? value : null;

    /// <summary>Formats a price or quantity the way the venue's query string expects it.</summary>
    /// <remarks>
    /// Fixed point, never scientific notation: a small quantity rendered as <c>1E-05</c> is rejected by
    /// the venue, and <c>decimal.ToString()</c> alone would also carry the trailing zeros of the value's
    /// scale into the signature.
    /// </remarks>
    public static string Number(decimal value) =>
        value.ToString("0.##########", CultureInfo.InvariantCulture);

    /// <summary>Number of significant fractional digits, used to read a scale off a tick or step size.</summary>
    public static int ScaleOf(decimal grid)
    {
        if (grid <= 0)
            return 0;

        // Strip the trailing zeros the venue pads its filters with ("0.01000000" is 2 decimals, not 8).
        var normalized = grid / 1.000000000000000000000000000000000m;
        var scale = (byte)((decimal.GetBits(normalized)[3] >> 16) & 0x7F);
        return scale;
    }
}
