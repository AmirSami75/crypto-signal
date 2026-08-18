using System.Text;
using System.Text.RegularExpressions;

namespace CryptoSignal.Infra.Helpers;

public static class PersianSlug
{
    public static string ToSlug(string input)
    {
        if (string.IsNullOrWhiteSpace(input))
            return string.Empty;

        var fa = Normalize(input);

        var sb = new StringBuilder(fa.Length * 2);

        for (int i = 0; i < fa.Length; i++)
        {
            var ch = fa[i];

            // space → dash
            if (char.IsWhiteSpace(ch))
            {
                sb.Append('-');
                continue;
            }

            sb.Append(MapChar(ch, i > 0 ? fa[i - 1] : (char?)null,
                i < fa.Length - 1 ? fa[i + 1] : (char?)null));
        }

        var slug = sb.ToString().ToLowerInvariant();

        // clean
        slug = Regex.Replace(slug, @"[^a-z0-9-]+", "-");
        slug = Regex.Replace(slug, "-{2,}", "-").Trim('-');

        return slug;
    }

    private static string Normalize(string input)
    {
        return input.Trim()
            .Replace('ك', 'ک')
            .Replace('ي', 'ی')
            .Replace('ۀ', 'ه')
            .Replace('ة', 'ه')
            .Replace("‌", "-") // ZWNJ
            .Replace("ـ", ""); // tatweel
    }

    private static string MapChar(char ch, char? prev, char? next)
    {
        return ch switch
        {
            'آ' => "a", 'ا' => "a",
            'ب' => "b", 'پ' => "p",
            'ت' => "t", 'ث' => "s",
            'ج' => "j", 'چ' => "ch",
            'ح' => "h", 'خ' => "kh",
            'د' => "d", 'ذ' => "z",
            'ر' => "r", 'ز' => "z", 'ژ' => "zh",
            'س' => "s", 'ش' => "sh",
            'ص' => "s", 'ض' => "z",
            'ط' => "t", 'ظ' => "z",
            'ع' => "a", 'غ' => "gh",
            'ف' => "f", 'ق' => "q",
            'ک' => "k", 'گ' => "g",
            'ل' => "l", 'م' => "m", 'ن' => "n",
            'ه' => HandleHe(prev, next),
            'و' => HandleVav(prev, next),
            'ی' => HandleYa(prev, next),
            '-' => "-",
            _ => ""
        };
    }

    private static string HandleVav(char? prev, char? next)
    {
        // consonant sandwich → 'o'
        if (IsConsonant(prev) && IsConsonant(next))
            return "o";

        return "v";
    }

    private static string HandleYa(char? prev, char? next)
    {
        // start of word → y
        if (prev is null || prev == '-' || char.IsWhiteSpace(prev.Value))
            return "y";

        return "i";
    }

    private static string HandleHe(char? prev, char? next)
    {
        if (IsConsonant(prev) && IsConsonant(next))
            return "eh";

        return "h";
    }

    private static bool IsConsonant(char? ch)
    {
        if (ch is null) return false;

        return ch switch
        {
            'ا' or 'و' or 'ی' or 'آ' => false,
            >= '\u0600' and <= '\u06FF' => true,
            _ => false
        };
    }
}