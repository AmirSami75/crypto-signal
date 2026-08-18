using System.Security.Cryptography;
using System.Text;

namespace CryptoSignal.Infra.Helpers;

public class Crypto
{
    public static string GeneratePassword(int lowercase = 1, int uppercase = 1, int numerics = 5)
    {
        string lowers = "abcdefghijklmnopqrstuvwxyz";
        string uppers = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        string number = "0123456789";

        Random random = new Random();

        string generated = "!";
        for (int i = 1; i <= lowercase; i++)
            generated = generated.Insert(
                random.Next(generated.Length),
                lowers[random.Next(lowers.Length - 1)].ToString()
            );

        for (int i = 1; i <= uppercase; i++)
            generated = generated.Insert(
                random.Next(generated.Length),
                uppers[random.Next(uppers.Length - 1)].ToString()
            );

        for (int i = 1; i <= numerics; i++)
            generated = generated.Insert(
                random.Next(generated.Length),
                number[random.Next(number.Length - 1)].ToString()
            );

        return generated;

    }

    public static string GetSha256Hash(string input)
    {
        using (var sha256 = SHA256.Create())
        {
            var byteValue = Encoding.UTF8.GetBytes(input);
            var byteHash = sha256.ComputeHash(byteValue);
            return Convert.ToBase64String(byteHash);
        }
    }

    public static string Md5Signature(Stream stream)
    {
        using var md5 = MD5.Create();
        var hashBytes = md5.ComputeHash(stream);
        var builder = new StringBuilder();
        foreach (var t in hashBytes)
        {
            builder.Append(t.ToString("x2"));
        }

        return builder.ToString();
    }

}
