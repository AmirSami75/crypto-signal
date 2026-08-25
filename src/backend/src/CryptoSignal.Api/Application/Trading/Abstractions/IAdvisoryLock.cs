namespace CryptoSignal.Api.Application.Trading.Abstractions;

/// <summary>
/// A cross-connection mutex keyed by a 64-bit id, used to keep exactly one worker on one bot's tick.
/// </summary>
/// <remarks>
/// <para>
/// The lease row on <see cref="Domain.Models.Trading.BotRun"/> records <em>who</em> holds a bot and
/// <em>when</em> it last proved alive, but a row cannot enforce mutual exclusion — two replicas can read
/// "unheld" in the same instant and both write. This lock is the enforcement: a Postgres advisory lock
/// is held by a database session, and a second acquirer is refused immediately rather than made to wait.
/// </para>
/// <para>
/// A refused acquisition is a normal outcome, not an error — it means another worker already has the bot,
/// and this worker should simply skip it this cycle.
/// </para>
/// </remarks>
public interface IAdvisoryLock
{
    /// <summary>
    /// Tries to take the lock for <paramref name="key"/>. Returns a handle to release on dispose, or null
    /// when another session holds it. Never blocks.
    /// </summary>
    Task<IAsyncDisposable?> TryAcquireAsync(long key, CancellationToken cancellationToken);
}
