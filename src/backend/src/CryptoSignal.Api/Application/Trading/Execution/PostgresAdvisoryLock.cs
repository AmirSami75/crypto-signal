using System.Data;
using System.Data.Common;
using CryptoSignal.Api.Adapter.Persistence.Contexts;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.Application.Trading.Execution;

/// <summary>
/// <see cref="IAdvisoryLock"/> over <c>pg_try_advisory_lock</c> / <c>pg_advisory_unlock</c>.
/// </summary>
/// <remarks>
/// <para>
/// Session-level, not transaction-level, and that choice is deliberate: a tick spans several
/// transactions — persist the window, persist the decision, place the order, record the fill — and a
/// <c>pg_advisory_xact_lock</c> would release at the first commit, unlocking the bot mid-tick. The lock
/// must outlive every transaction inside the tick, so it is taken and released explicitly on one
/// dedicated connection this class owns for the lock's lifetime.
/// </para>
/// <para>
/// Because the lock lives on a single physical connection, that connection is opened here and held until
/// release, never borrowed from the pooled DbContext whose connection EF may reset between calls. The
/// handle's <c>DisposeAsync</c> is what unlocks; a worker that faults still releases through the
/// <c>await using</c> in the caller.
/// </para>
/// </remarks>
public sealed class PostgresAdvisoryLock(
    CryptoSignalDbContext dbContext,
    ILogger<PostgresAdvisoryLock> logger) : IAdvisoryLock, IScopedSvcMarker
{
    public async Task<IAsyncDisposable?> TryAcquireAsync(long key, CancellationToken cancellationToken)
    {
        // A connection of our own. The pooled EF connection can be reset between commands, which would
        // drop a session-level lock; this one is held open for exactly as long as the lock is.
        var connection = dbContext.Database.GetDbConnection();
        var openedHere = false;

        if (connection.State != ConnectionState.Open)
        {
            await connection.OpenAsync(cancellationToken);
            openedHere = true;
        }

        bool acquired;
        await using (var command = connection.CreateCommand())
        {
            command.CommandText = "SELECT pg_try_advisory_lock(@key)";
            command.Parameters.Add(Parameter(command, "@key", key));
            var result = await command.ExecuteScalarAsync(cancellationToken);
            acquired = result is true;
        }

        if (!acquired)
        {
            // Someone else holds this bot. Not an error — just not our turn.
            if (openedHere)
                await connection.CloseAsync();
            return null;
        }

        logger.LogDebug("Acquired advisory lock {Key}", key);
        return new Handle(connection, key, openedHere, logger);
    }

    private static DbParameter Parameter(DbCommand command, string name, long value)
    {
        var parameter = command.CreateParameter();
        parameter.ParameterName = name;
        parameter.DbType = DbType.Int64;
        parameter.Value = value;
        return parameter;
    }

    /// <summary>Releases the lock on dispose, and only then closes a connection it opened.</summary>
    private sealed class Handle(
        DbConnection connection,
        long key,
        bool closeOnDispose,
        ILogger logger) : IAsyncDisposable
    {
        public async ValueTask DisposeAsync()
        {
            try
            {
                await using var command = connection.CreateCommand();
                command.CommandText = "SELECT pg_advisory_unlock(@key)";
                command.Parameters.Add(Parameter(command, "@key", key));
                await command.ExecuteScalarAsync();
                logger.LogDebug("Released advisory lock {Key}", key);
            }
            catch (Exception exception)
            {
                // The lock also releases when the session ends, so a failed explicit unlock is a leak
                // that heals itself rather than a stuck bot forever.
                logger.LogWarning(exception, "Failed to release advisory lock {Key}", key);
            }
            finally
            {
                if (closeOnDispose)
                    await connection.CloseAsync();
            }
        }
    }
}
