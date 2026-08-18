using Microsoft.AspNetCore.Http;
using Path = System.IO.Path;

namespace CryptoSignal.Infra.Extensions.SaveFile
{
    public static class SaveFileExtention
    {
        private static readonly string[] AllowedExtensions = [".jpg", ".jpeg", ".png"];
        private const long MaxFileSizeBytes = 50 * 1024 * 1024; // 5MB

        public static async Task<string> SaveFileAsync(this IFormFile? file, string nameAction, CancellationToken ct)
        {
            if (file == null || file.Length == 0)
                return string.Empty;

            if (file.Length > MaxFileSizeBytes)
                throw new InvalidOperationException("حجم فایل از حد مجاز بیشتر است.");

            var ext = Path.GetExtension(file.FileName).ToLowerInvariant();
            if (!AllowedExtensions.Contains(ext))
                throw new InvalidOperationException("فرمت فایل مجاز نیست.");

            var uploadsFolder = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "uploads", nameAction);
            if (!Directory.Exists(uploadsFolder))
                Directory.CreateDirectory(uploadsFolder);

            var fileName = $"{Guid.NewGuid()}{ext}";
            var filePath = Path.Combine(uploadsFolder, fileName);

            await using var stream = new FileStream(filePath, FileMode.Create);
            await file.CopyToAsync(stream, ct);

            return $"uploads/{nameAction}/{fileName}";
        }
    }
}
