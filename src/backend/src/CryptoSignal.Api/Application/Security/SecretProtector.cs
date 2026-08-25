using System.Collections.Concurrent;
using System.Security.Cryptography;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.Application.Security;

/// <summary>Binding for <c>Sercurity</c> (kept to the existing config section spelling).</summary>
public sealed class KeyProtectionOptions
{
    public const string SectionName = "Sercurity";

    /// <summary>
    /// Base64 32-byte key for AES-GCM. Server-side only: absent or malformed means connections cannot
    /// be written, which fails closed rather than falling back to storing plaintext.
    /// </summary>
    public string KeyEncryptionKey { get; init; } = string.Empty;
}

/// <summary>
/// AES-GCM sealing and opening for exchange credentials at rest.
/// </summary>
/// <remarks>
/// <para>
/// GCM rather than CBC because a tampered ciphertext should fail authentication, not decrypt into
/// plausible-looking garbage that then gets HMAC-signed and sent to an exchange. The nonce is random
/// per call and prepended to the output — never reused with the same key.
/// </para>
/// <para>
/// The master key is parsed once and cached. A malformed key throws on first use, which surfaces as a
/// failed connection write at request time; startup validation in Program.cs catches it earlier.
/// </para>
/// </remarks>
public sealed class SecretProtector(IOptions<KeyProtectionOptions> options)
{
    private static readonly ConcurrentDictionary<byte[], byte[]> KeyCache = new();

    private byte[] MasterKey =>
        KeyCache.GetOrAdd(
            DecodeKey(options.Value.KeyEncryptionKey),
            static key => key);

    private static byte[] DecodeKey(string configured) =>
        Convert.FromBase64String(string.IsNullOrWhiteSpace(configured)
            ? throw new InvalidOperationException(
                "Sercurity:KeyEncryptionKey is not configured. Exchange API keys cannot be stored " +
                "without it — set a base64 32-byte value via API_Settings__Sercurity__KeyEncryptionKey.")
            : configured);

    public string Seal(string plaintext)
    {
        var nonce = RandomNumberGenerator.GetBytes(12);
        var ciphertext = new byte[plaintext.Length];
        var tag = new byte[16];

        using var gcm = new AesGcm(MasterKey, AesGcm.TagByteSizes.MaxSize);
        gcm.Encrypt(nonce, System.Text.Encoding.UTF8.GetBytes(plaintext), ciphertext, tag);

        // nonce || ciphertext || tag — one opaque blob per row.
        var payload = new byte[nonce.Length + ciphertext.Length + tag.Length];
        Buffer.BlockCopy(nonce, 0, payload, 0, nonce.Length);
        Buffer.BlockCopy(ciphertext, 0, payload, nonce.Length, ciphertext.Length);
        Buffer.BlockCopy(tag, 0, payload, nonce.Length + ciphertext.Length, tag.Length);

        return Convert.ToBase64String(payload);
    }

    public string Open(string sealedText)
    {
        var payload = Convert.FromBase64String(sealedText);
        if (payload.Length < 12 + 16)
            throw new CryptographicException("The stored credential blob is truncated.");

        var nonce = payload.AsSpan(0, 12);
        var ciphertext = payload.AsSpan(12, payload.Length - 28);
        var tag = payload.AsSpan(payload.Length - 16, 16);
        var plaintext = new byte[ciphertext.Length];

        using var gcm = new AesGcm(MasterKey, AesGcm.TagByteSizes.MaxSize);
        gcm.Decrypt(nonce, ciphertext, tag, plaintext);

        return System.Text.Encoding.UTF8.GetString(plaintext);
    }
}
