namespace CryptoSignal.Infra.Extensions.Contracts;

public interface IStringNormalizer
{
    /// <summary>Normalize a string: trim, fix Persian chars, convert digits Fa/Ar->En, collapse spaces, return null if empty.</summary>
    string? Normalize(string? input);
}