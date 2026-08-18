namespace CryptoSignal.Infra.Extensions.Type;

public static class EnumerableChunkExtension
{
    public static IEnumerable<List<T>> ToChunk<T>(this IEnumerable<T> source, int size)
    {
        var list = new List<T>(size);
        foreach (var item in source)
        {
            list.Add(item);
            if (list.Count == size)
            {
                yield return list;
                list = new List<T>(size);
            }
        }

        if (list.Count > 0) yield return list;
    }

    public static async IAsyncEnumerable<List<T>> ToChunkAsync<T>(
        this IEnumerable<T> source, int size,
        [System.Runtime.CompilerServices.EnumeratorCancellation]
        CancellationToken ct = default)
    {
        // synchronous enumerable -> async-friendly yield
        foreach (var chunk in source.ToChunk(size))
        {
            ct.ThrowIfCancellationRequested();
            yield return chunk;
            await Task.Yield();
        }
    }
}