using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Extensions.Type;

namespace CryptoSignal.Infra.Helpers;

public static class Common
{
    private static readonly CultureInfo Fa = new("fa-IR");
    private static readonly char[] EnNo = "0123456789".ToCharArray();
    private static readonly char[] FaNo = "۰۱۲۳۴۵۶۷۸۹".ToCharArray();
    private const char WordJoiner = '\u2060'; // prevents line wrap after comma

    /// <summary>
    /// Generates a random numeric string containing only digits (0–9).
    /// </summary>
    /// <param name="maxLength">The maximum length of the generated string. Must be greater than zero.</param>
    /// <returns>A random string of digits.</returns>
    /// <exception cref="ArgumentOutOfRangeException">Thrown when <paramref name="maxLength"/> is less than 1.</exception>
    public static string GenerateDigitNumber(int maxLength = 5)
    {
        if (maxLength < 1)
            throw new ArgumentOutOfRangeException(nameof(maxLength), "Length must be at least 1.");


        const string digits = "0123456789";
        var result = new StringBuilder(maxLength);

        // Use RandomNumberGenerator for cryptographically secure randomness
        var buffer = new byte[maxLength];
        RandomNumberGenerator.Fill(buffer);
        for (var i = 0; i < maxLength; i++)
        {
            var index = buffer[i] % digits.Length;
            result.Append(digits[index]);
        }

        return result.ToString();
    }

    public static string HumanizeSize(long bytes)
    {
        const long KB = 1024, MB = KB * 1024, GB = MB * 1024;
        return bytes switch
        {
            < KB => $"{bytes} B",
            < MB => $"{bytes / (double)KB:0.##} KB",
            < GB => $"{bytes / (double)MB:0.##} MB",
            _ => $"{bytes / (double)GB:0.##} GB"
        };
    }

    // Persianize any string’s digits (also trims weird newlines/spaces in dates)
    public static string ToFaDigits(string? s)
    {
        if (string.IsNullOrWhiteSpace(s)) return "—";
        s = s.Replace("\r", "").Replace("\n", " ").Trim();
        ReadOnlySpan<char> en = "0123456789";
        ReadOnlySpan<char> fa = "۰۱۲۳۴۵۶۷۸۹";
        Span<char> buf = stackalloc char[s.Length];
        for (int i = 0; i < s.Length; i++)
        {
            var c = s[i];
            int idx = en.IndexOf(c);
            buf[i] = idx >= 0 ? fa[idx] : c;
        }

        return buf.ToString();
    }

    // 174,154,055  ->  ۱۷۴,۱۵۴,۰۵۵  (keeps comma, adds no-wrap)
    public static string ToFaDigitsWithCommaNoBreak(this string s)
    {
        if (string.IsNullOrWhiteSpace(s)) return "—";

        Span<char> buf = stackalloc char[s.Length * 2];
        var j = 0;
        foreach (var c in s)
        {
            if (c is >= '0' and <= '9')
                buf[j++] = FaNo[c - '0']; // convert digits
            else
            {
                buf[j++] = c; // keep punctuation (comma, slash, …)
                if (c == ',') // avoid line breaks inside numbers
                    buf[j++] = WordJoiner;
            }
        }

        return new string(buf[..j]);
    }

    public static string MoneyFaComma(this decimal? v)
        => v.HasValue
            ? v.Value.ToString("#,0", CultureInfo.InvariantCulture)
                .ToFaDigitsWithCommaNoBreak()
            : "—";

    // Money → Persian digits + Persian thousands separator (e.g., ۱٬۷۴۴٬۱۵۵)
    public static string Money(decimal? v) => MoneyFaComma(v);

    // Percent shown already in percent scale (e.g., ۱۲٫۵ %)
    public static string Pct100(decimal? v) =>
        v.HasValue ? ToFaDigits(v.Value.ToString("0.#", Fa)) + " %" : "—";

    // Dates are strings in your DTO; just Persianize digits + collapse spaces.
    public static string DateFa(string? s) => ToFaDigits(s);

    // Generic fallback
    public static string DashFa(string? s) => ToFaDigits(s);

    public static string BoolFa(bool v) => v ? "بله" : "خیر";

    public static string GenerateUniqueIdentifierByDate() =>
        $"{DateTime.Now.ConvertToPersianDate(timeSeparator: "", dateSeparator: "")}";
}