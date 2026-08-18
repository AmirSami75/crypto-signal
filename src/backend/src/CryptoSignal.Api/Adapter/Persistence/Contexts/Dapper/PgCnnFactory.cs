using System.Data;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Infra.Settings;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using Microsoft.Extensions.Options;
using Npgsql;

namespace CryptoSignal.Api.Adapter.Persistence.Contexts.Dapper;

/// <inheritdoc cref="IPgCnnFactory"/>
public sealed class PgCnnFactory(IOptions<DbSettings> dbSettings, ILoggerAdapter<PgCnnFactory> logger)
    : IPgCnnFactory, IScopedSvcMarker
{
    private readonly string _connectionString =
        dbSettings.Value.PostgreSqlCnnStr
        ?? throw new InvalidOperationException("API_Settings:Db:PostgreSqlCnnStr is required.");

    public async Task<IDbConnection> CreateOpenConnectionAsync(CancellationToken ct = default)
    {
        var connection = new NpgsqlConnection(_connectionString);

        try
        {
            await connection.OpenAsync(ct);
            logger.Debug("PostgreSQL connection opened to {DataSource}/{Database}",
                connection.DataSource, connection.Database);
            return connection;
        }
        catch (Exception ex)
        {
            // Dispose before rethrowing: the caller never receives the connection, so nothing
            // else can return it to the pool.
            await connection.DisposeAsync();
            logger.Error(ex, "Failed to open a PostgreSQL connection.");
            throw;
        }
    }
}
