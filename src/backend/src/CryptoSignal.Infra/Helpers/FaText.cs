using System.Text;
using System.Text.RegularExpressions;

namespace CryptoSignal.Infra.Helpers;

public static class FaText
{
    private const char Zwnj = '\u200C';
    private const char Rlm  = '\u200F';
    private const char Tatweel = '\u0640';
    private const char Nbsp = '\u00A0';
    private const char HamzaAbove = '\u0654';
    private const char Heh = '\u0647';

    private static readonly Dictionary<char, char> Map = new()
    {
        ['ي']='ی', ['ك']='ک',
        ['٠']='0', ['١']='1', ['٢']='2', ['٣']='3', ['٤']='4',
        ['٥']='5', ['٦']='6', ['٧']='7', ['٨']='8', ['٩']='9',
        ['۰']='0', ['۱']='1', ['۲']='2', ['۳']='3', ['۴']='4',
        ['۵']='5', ['۶']='6', ['۷']='7', ['۸']='8', ['۹']='9'
    };

    private static readonly Regex WsRegex         = new(@"[ \t\r\n]+", RegexOptions.Compiled);
    private static readonly Regex HehHamzaRegex   = new($@"{Heh}{Zwnj}?{HamzaAbove}", RegexOptions.Compiled);
    private static readonly Regex MultiSpaceRegex = new(@"[ ]{2,}", RegexOptions.Compiled);

    public static string NormalizeCanonical(string? s)
    {
        if (string.IsNullOrWhiteSpace(s)) return string.Empty;
        var trimmed  = s.Trim().Replace(Nbsp, ' ');
        var filtered = new string(trimmed.Where(ch => ch != Rlm && ch != Tatweel).ToArray());
        var mapped   = filtered.Select(ch => Map.TryGetValue(ch, out var r) ? r : ch);
        var norm     = new string(mapped.ToArray()).Normalize(NormalizationForm.FormC);
        norm = WsRegex.Replace(norm, " ").Trim();
        norm = HehHamzaRegex.Replace(norm, $"{Heh}{Zwnj}{HamzaAbove}");
        return norm;
    }

    public static string NormalizeFa(string input)
    {
        if (string.IsNullOrWhiteSpace(input))
            return string.Empty;

        return input.Trim()
            .Replace('ك', 'ک')
            .Replace('ي', 'ی')
            .Replace("‌", "")   // ZWNJ
            .Replace("ـ", "")   // Tatweel
            .Replace("  ", " ");
    }
    
    
    public static string NormalizeToSpaces(string? s)
    {
        var canon = NormalizeCanonical(s);
        if (canon.Length == 0) return canon;
        var withSpaces = canon.Replace(Zwnj, ' ');
        return MultiSpaceRegex.Replace(withSpaces, " ").Trim();
    }

    public static bool CanonicalEquals(string? a, string? b)
        => string.Equals(NormalizeCanonical(a), NormalizeCanonical(b), StringComparison.Ordinal);

    public static bool SpacewiseEquals(string? a, string? b)
        => string.Equals(NormalizeToSpaces(a), NormalizeToSpaces(b), StringComparison.Ordinal);

    public static string MakeSpacewiseKey(string? s) => NormalizeToSpaces(s);

    // --- Real comparers you can pass to dictionaries ---
    public static IEqualityComparer<string> CanonicalComparer { get; } = new CanonicalEq();
    public static IEqualityComparer<string> SpacewiseComparer { get; } = new SpacewiseEq();

    private sealed class CanonicalEq : IEqualityComparer<string>
    {
        public bool Equals(string? x, string? y) => CanonicalEquals(x, y);
        public int GetHashCode(string obj) => NormalizeCanonical(obj).GetHashCode();
    }

    
        
    private sealed class SpacewiseEq : IEqualityComparer<string>
    {
        public bool Equals(string? x, string? y) => SpacewiseEquals(x, y);
        public int GetHashCode(string obj) => NormalizeToSpaces(obj).GetHashCode();
    }
}
