using CryptoSignal.Api.Contracts;

namespace CryptoSignal.Api.Clients;

/// <summary>
/// The .NET-facing wrapper around the Python ML engine's gRPC surface. Everything here is advisory:
/// the engine answers questions about a market, and no method on it places, authorizes, or sizes an
/// order — that is the orchestrator's, and only the orchestrator's, to do (see <c>docs/ARCHITECTURE.md</c>).
/// </summary>
public interface IMlServiceClient
{
    Task<DependencyHealth> GetHealthAsync(CancellationToken cancellationToken);

    Task<MlServiceCapabilities?> GetCapabilitiesAsync(CancellationToken cancellationToken);

    /// <summary>Metadata for the model that answers a given market; empty symbol resolves the wildcard.</summary>
    Task<MlModelInfo?> GetModelInfoAsync(
        string symbol,
        string interval,
        CancellationToken cancellationToken);

    /// <summary>Capability 2: a one-off signal for a market at requested barriers.</summary>
    Task<MlSignal> GetSignalAsync(
        MlSignalRequest request,
        CancellationToken cancellationToken);

    /// <summary>Capability 1's advisor: what to do next given a bot's configuration and open position.</summary>
    Task<MlBotDecision> EvaluateBotDecisionAsync(
        MlBotDecisionRequest request,
        CancellationToken cancellationToken);
}
