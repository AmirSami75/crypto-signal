namespace CryptoSignal.Infra.Helpers;

public static class FaLegacyVariants
{
    private const char Zwnj = '\u200C';
    private const char HamzaAbove = '\u0654';
    private const char Heh = '\u0647';
    private const char PersianYeh = '\u06CC';
    private const char HamzayedYeh = '\u0626'; // ئ

    // Build all legacy variants we’ve seen in the wild:
    // - ZWNJ kept, removed, or replaced with space
    // - Heh + HamzaAbove (هٔ) → Yeh+Heh (یه)
    // - Remove hamza above
    // - ئ → ی
    public static IEnumerable<string> TitleCandidates(string canonical)
    {
        var set = new HashSet<string> { canonical };

        void Add(string s)
        {
            if (!set.Contains(s)) set.Add(s);
        }

        // Basic ZWNJ variants
        Add(NoZwnj(canonical));
        Add(ZwnjToSpace(canonical));

        // Hamza variants
        Add(RemoveHamza(canonical));
        Add(HehHamzaToYehHeh(canonical));

        // Combine hamza + ZWNJ variants
        var noZ = NoZwnj(canonical);
        Add(RemoveHamza(noZ));
        Add(HehHamzaToYehHeh(noZ));

        var zToSp = ZwnjToSpace(canonical);
        Add(RemoveHamza(zToSp));
        Add(HehHamzaToYehHeh(zToSp));

        // ئ → ی fallback (some inputs store ئ as ی)
        foreach (var s in set.ToArray())
            Add(HamzayedYehToYeh(s));

        return set;

        string HamzayedYehToYeh(string s)  => s.Replace(HamzayedYeh.ToString(), PersianYeh.ToString());

        string HehHamzaToYehHeh(string s) => s.Replace($"{Heh}{HamzaAbove}", $"{PersianYeh}{Heh}");

        string RemoveHamza(string s) => s.Replace(HamzaAbove.ToString(), string.Empty);

        string ZwnjToSpace(string s) => s.Replace(Zwnj.ToString(), " ");

        string NoZwnj(string s)      => s.Replace(Zwnj.ToString(), string.Empty);
    }
}