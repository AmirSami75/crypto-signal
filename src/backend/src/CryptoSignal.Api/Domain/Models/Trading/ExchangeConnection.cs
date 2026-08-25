using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// One operator-supplied set of API credentials for one exchange venue, owned by one user.
/// </summary>
/// <remarks>
/// <para>
/// <b>The secret is never stored in the clear and never leaves the server once written.</b> It arrives
/// over TLS on a create/update call, is encrypted with AES-GCM under a server-side key, and is decrypted
/// only in memory at the moment a signed request is built. The plaintext secret is never returned by any
/// endpoint; responses carry <see cref="KeyPreview"/> — the last four characters — so the operator can
/// tell which key row is which without the store ever holding or showing enough to trade with.
/// </para>
/// <para>
/// One user may hold several connections per venue (a main account and a sub-account, say); bots pin to
/// one connection by id. <see cref="IsActive"/> is the kill path for a credential without deleting it —
/// deactivating makes it unresolvable immediately, so an active bot using it faults on its next tick
/// rather than trading on a key the operator just revoked.
/// </para>
/// </remarks>
public class ExchangeConnection : BaseEntity
{
    /// <summary>Owner. Connections are per-user; another user can neither see nor resolve them.</summary>
    public Guid UserId { get; set; }

    /// <summary>Which venue these credentials speak to.</summary>
    public MarketVenue Venue { get; set; }

    /// <summary>Operator-facing label, e.g. "main account". Not an identifier.</summary>
    public string Label { get; set; } = string.Empty;

    /// <summary>AES-GCM ciphertext of the API key. Base64.</summary>
    public string ApiKeyEncrypted { get; set; } = string.Empty;

    /// <summary>AES-GCM ciphertext of the API secret. Base64. Never decrypted into any response.</summary>
    public string ApiSecretEncrypted { get; set; } = string.Empty;

    /// <summary>Last four characters of the plaintext key, for recognition only.</summary>
    public string KeyPreview { get; set; } = string.Empty;

    /// <summary>False blocks resolution immediately — the revocation switch for a credential.</summary>
    public bool IsActive { get; set; } = true;

    /// <summary>When a test round-trip against the venue last succeeded, if it ever did.</summary>
    public DateTime? LastValidatedAt { get; set; }
}
