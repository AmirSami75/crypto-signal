using System.Security.Cryptography;
using System.Text;

namespace CryptoSignal.Api.Application.Trading.Execution;

/// <summary>
/// Derives the venue-facing client order id and the advisory-lock key deterministically, so a retry
/// produces the same values a first attempt did.
/// </summary>
/// <remarks>
/// <para>
/// The client order id is the idempotency key the exchange dedupes on. It <b>must</b> be a pure function
/// of the decision id and nothing else — not the clock, not a counter, not a fresh Guid — because the
/// whole point is that a worker retrying the same decision constructs the same id and the venue returns
/// the existing order instead of placing a second. That is also why the derivation lives here, in one
/// place, rather than being inlined where an "ok, just this once" could slip a timestamp into it.
/// </para>
/// <para>
/// Binance restricts a spot client order id to <c>^[\.A-Z\:/a-z0-9_-]{1,36}$</c>. The <c>cs-</c> prefix
/// plus 32 lowercase hex characters is 35 — inside the limit, and readable enough to grep for in a venue
/// dashboard.
/// </para>
/// </remarks>
public static class TradingIdentifiers
{
    private const string ClientOrderPrefix = "cs-";

    /// <summary>The deterministic client order id for the one order a decision authorises.</summary>
    public static string ClientOrderId(Guid strategyDecisionId)
    {
        // The decision id alone is enough: a decision authorises exactly one order, which the unique
        // index on OrderIntent.StrategyDecisionId enforces.
        var hash = SHA256.HashData(Encoding.ASCII.GetBytes(strategyDecisionId.ToString("N")));

        // 16 bytes of the digest -> 32 hex characters. Truncation is safe here because the input is
        // already a unique id; the hash is only being used to shorten and charset-normalise it.
        return ClientOrderPrefix + Convert.ToHexStringLower(hash.AsSpan(0, 16));
    }

    /// <summary>
    /// A stable 64-bit advisory-lock key for a bot. Postgres advisory locks are keyed by <c>bigint</c>,
    /// so the bot's Guid is folded into 64 bits.
    /// </summary>
    /// <remarks>
    /// A collision would let two <em>different</em> bots serialise against one lock — a performance
    /// nuisance, never a safety fault: the worst case is one bot waiting a cycle for an unrelated one,
    /// and the per-bot lease and unique run index remain the real correctness guarantees.
    /// </remarks>
    public static long AdvisoryLockKey(Guid botId)
    {
        Span<byte> bytes = stackalloc byte[16];
        botId.TryWriteBytes(bytes);
        return BitConverter.ToInt64(bytes[..8]) ^ BitConverter.ToInt64(bytes[8..]);
    }
}
