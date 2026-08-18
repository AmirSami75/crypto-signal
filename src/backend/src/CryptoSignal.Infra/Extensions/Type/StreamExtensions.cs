namespace CryptoSignal.Infra.Extensions.Type;

public static class StreamExtensions
{
    public static string ToBase64(this Stream stream)
    {
        if (stream is MemoryStream memoryStream)
            return Convert.ToBase64String(memoryStream.ToArray());

        var bytes = new byte[(int)stream.Length];

        stream.Seek(0, SeekOrigin.Begin);
        stream.Read(bytes, 0, (int)stream.Length);

        return Convert.ToBase64String(bytes);
    }
}
