using Microsoft.AspNetCore.Http;

namespace CryptoSignal.Infra.Extensions.Type;

public static class IFormFileExtentions
{
    private static readonly List<byte[]> ImageMagicNumbers = new List<byte[]>
        {
            new byte[] { 0xFF, 0xD8, 0xFF, 0xE0 }, // JPEG
			new byte[] { 0x89, 0x50, 0x4E, 0x47 }, // PNG
			new byte[] { 0x47, 0x49, 0x46, 0x38 }, // GIF
		};

    public static bool IsImage(this IFormFile file)
    {
        using var stream = file.OpenReadStream();
        byte[] header = new byte[4];
        stream.Read(header, 0, 4);

        foreach (var magicNumber in ImageMagicNumbers)
        {
            if (header.SequenceEqual(magicNumber))
            {
                return true;
            }
        }
        return false;
    }

    public static byte[] ToByteArray(this IFormFile formFile)
    {
        using var memoryStream = new MemoryStream();
        formFile.CopyTo(memoryStream);
        return memoryStream.ToArray();
    }

    public static string ToBase64(this IFormFile formFile)
    {
        return Convert.ToBase64String(ToByteArray(formFile));
    }
}
