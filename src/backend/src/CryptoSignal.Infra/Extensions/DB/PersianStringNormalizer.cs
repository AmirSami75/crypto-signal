using System.Text;
using CryptoSignal.Infra.Extensions.Contracts;

namespace CryptoSignal.Infra.Extensions.DB;

public class PersianStringNormalizer : IStringNormalizer
{
    private static readonly Dictionary<char, char> Map = new()
    {
        // Arabic/Persian digits -> Latin
        ['۰'] = '0', ['۱'] = '1', ['۲'] = '2', ['۳'] = '3', ['۴'] = '4', ['۵'] = '5', ['۶'] = '6', ['۷'] = '7',
        ['۸'] = '8', ['۹'] = '9',
        ['٠'] = '0', ['١'] = '1', ['٢'] = '2', ['٣'] = '3', ['٤'] = '4', ['٥'] = '5', ['٦'] = '6', ['٧'] = '7',
        ['٨'] = '8', ['٩'] = '9',
        // Arabic forms -> Persian
        ['ك'] = 'ک', ['ي'] = 'ی', ['ھ'] = 'ه',
        // Presentation forms of Kaf -> Kaf
        ['ﮎ'] = 'ک', ['ﮏ'] = 'ک', ['ﮐ'] = 'ک', ['ﮑ'] = 'ک',
    };

    public string? Normalize(string? input)
    {
        if (string.IsNullOrWhiteSpace(input))
            return null;

        var span = input.AsSpan();
        var sb = new StringBuilder(span.Length);

        foreach (var t in span)
        {
            var ch = t;

            // unify NBSP and ZWNJ to space
            if (ch is '\u00A0' or '\u200C')
                ch = ' ';

            sb.Append(Map.TryGetValue(ch, out var mapped) ? mapped : ch);
        }

        // collapse multiple spaces and trim
        var normalized = CollapseSpaces(sb.ToString()).Trim();

        return normalized.Length == 0 ? null : normalized;

        static string CollapseSpaces(string s)
        {
            // cheap single pass for consecutive spaces
            var sb = new StringBuilder(s.Length);
            var prevSpace = false;
            foreach (var c in s)
            {
                if (c == ' ')
                {
                    if (!prevSpace) sb.Append(c);
                    prevSpace = true;
                }
                else
                {
                    sb.Append(c);
                    prevSpace = false;
                }
            }

            return sb.ToString();
        }
    }
}