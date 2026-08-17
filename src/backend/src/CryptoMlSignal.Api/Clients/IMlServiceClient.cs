using CryptoMlSignal.Api.Contracts;

namespace CryptoMlSignal.Api.Clients;

public interface IMlServiceClient
{
    Task<DependencyHealth> GetHealthAsync(CancellationToken cancellationToken);

    Task<MlServiceCapabilities?> GetCapabilitiesAsync(
        CancellationToken cancellationToken);

    Task<MlModelInfo?> GetModelInfoAsync(CancellationToken cancellationToken);

    Task<MlPrediction> PredictSignalAsync(
        MlPredictionRequest request,
        CancellationToken cancellationToken);
}
