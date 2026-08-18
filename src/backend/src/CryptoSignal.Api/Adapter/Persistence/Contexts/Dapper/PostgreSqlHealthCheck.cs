using System.Data.Common;
using Dapper;
using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace CryptoSignal.Api.Adapter.Persistence.Contexts.Dapper;

/// <summary>
/// Reports whether PostgreSQL is reachable and answering queries.
/// </summary>
public sealed class PostgreSqlHealthCheck(IPgCnnFactory factory) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context,
        CancellationToken ct = default)
    {
        try
        {
            await using var connection = (DbConnection)await factory.CreateOpenConnectionAsync(ct);

            var probe = await connection.ExecuteScalarAsync<string>(
                new CommandDefinition("SELECT 'OK'", cancellationToken: ct));

            return probe == "OK"
                ? HealthCheckResult.Healthy()
                : HealthCheckResult.Unhealthy($"Unexpected probe result: '{probe}'.");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("PostgreSQL is not reachable.", ex);
        }
    }
}
