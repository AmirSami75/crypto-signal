using Microsoft.Extensions.Diagnostics.HealthChecks;
using CryptoSignal.Api.Clients;

namespace CryptoSignal.Api.Adapter.Health;

/// <summary>
/// Health of the Python inference service.
///
/// A degraded (not unhealthy) verdict is deliberate: the API keeps serving history, auth, and the
/// dashboard while the engine is down — what breaks is signal generation and bot ticks, and the
/// scheduler already faults bots on a failed consult. Reporting "unhealthy" would make orchestrators
/// restart an API whose only problem is a neighbour, without fixing the neighbour.
/// </summary>
public sealed class MlEngineHealthCheck(IMlServiceClient ml) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var capabilities = await ml.GetCapabilitiesAsync(cancellationToken);
            if (capabilities is null)
                return new HealthCheckResult(HealthStatus.Degraded, "ML engine returned no capabilities");

            // Capabilities without a ready model is the "process up, product down" state: the gRPC
            // service answers but every consult would fail. Say which half works.
            return capabilities.ModelReady || capabilities.WildcardModelReady
                ? HealthCheckResult.Healthy($"engine {capabilities.ServiceVersion}, model ready")
                : new HealthCheckResult(HealthStatus.Degraded, $"engine {capabilities.ServiceVersion} reachable but no model is loaded");
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return new HealthCheckResult(HealthStatus.Degraded, $"ML engine unreachable: {exception.Message}");
        }
    }
}
