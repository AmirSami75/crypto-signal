namespace CryptoSignal.Infra.Helpers;

public static class EfUtils
{
    public static void ReplaceChildren<T>(
        ICollection<T> tracked,
        IEnumerable<T> replacement,
        Action<T>? setFk = null)
    {
        tracked.Clear();
        foreach (var e in replacement)
        {
            setFk?.Invoke(e);
            tracked.Add(e);
        }
    }
}