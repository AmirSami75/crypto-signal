using CryptoSignal.Contracts.Ml.V1;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Api.Application.Options;
using Google.Protobuf.WellKnownTypes;
using Grpc.Core;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.Clients;

public sealed class MlServiceClient(
    MlEngineService.MlEngineServiceClient client,
    IOptions<MlServiceOptions> options,
    ILogger<MlServiceClient> logger)
    : IMlServiceClient
{
    public async Task<DependencyHealth> GetHealthAsync(
        CancellationToken cancellationToken)
    {
        try
        {
            var response = await client.GetModelInfoAsync(
                new GetModelInfoRequest { RequestId = Guid.NewGuid().ToString() },
                deadline: Deadline(),
                cancellationToken: cancellationToken);
            return new DependencyHealth(
                "python-ml",
                response.Ready ? "healthy" : "unhealthy",
                response.Ready ? $"model={response.ModelId}" : "model not ready");
        }
        catch (RpcException exception)
        {
            logger.LogWarning(exception, "Python ML gRPC health check failed");
            return new DependencyHealth(
                "python-ml",
                "unavailable",
                $"gRPC {exception.StatusCode}: {exception.Status.Detail}");
        }
    }

    public async Task<MlServiceCapabilities?> GetCapabilitiesAsync(
        CancellationToken cancellationToken)
    {
        try
        {
            var response = await client.GetCapabilitiesAsync(
                new GetCapabilitiesRequest { RequestId = Guid.NewGuid().ToString() },
                deadline: Deadline(),
                cancellationToken: cancellationToken);
            return new MlServiceCapabilities(
                response.Service,
                response.ServiceVersion,
                response.ProtocolVersion,
                response.Capabilities.ToArray(),
                response.SupportedOperations.ToArray(),
                response.ModelReady,
                response.MinimumCandles,
                response.MaximumCandles);
        }
        catch (RpcException exception)
        {
            logger.LogWarning(exception, "Python ML gRPC capability request failed");
            return null;
        }
    }

    public async Task<MlModelInfo?> GetModelInfoAsync(
        CancellationToken cancellationToken)
    {
        try
        {
            var response = await client.GetModelInfoAsync(
                new GetModelInfoRequest { RequestId = Guid.NewGuid().ToString() },
                deadline: Deadline(),
                cancellationToken: cancellationToken);
            return new MlModelInfo(
                response.Ready,
                response.ModelId,
                response.ModelVersion,
                response.ProjectVersion,
                response.Symbol,
                response.Interval,
                response.TrainedAt.ToDateTimeOffset(),
                response.FeatureCount,
                response.ProbabilityThreshold,
                response.SellSemantics);
        }
        catch (RpcException exception)
        {
            logger.LogWarning(exception, "Python ML gRPC model-info request failed");
            return null;
        }
    }

    public async Task<MlPrediction> PredictSignalAsync(
        MlPredictionRequest request,
        CancellationToken cancellationToken)
    {
        var grpcRequest = new PredictSignalRequest
        {
            RequestId = string.IsNullOrWhiteSpace(request.RequestId)
                ? Guid.NewGuid().ToString()
                : request.RequestId,
            Symbol = request.Symbol,
            Interval = request.Interval,
            ExpectedModelVersion = request.ExpectedModelVersion ?? string.Empty,
        };
        grpcRequest.Candles.AddRange(request.Candles.Select(candle => new Candle
        {
            OpenTime = Timestamp.FromDateTimeOffset(candle.OpenTime),
            Open = candle.Open,
            High = candle.High,
            Low = candle.Low,
            Close = candle.Close,
            Volume = candle.Volume,
        }));

        try
        {
            var response = await client.PredictSignalAsync(
                grpcRequest,
                deadline: Deadline(),
                cancellationToken: cancellationToken);
            return new MlPrediction(
                response.RequestId,
                response.Signal.ToString().ToUpperInvariant(),
                response.NumericSignal,
                new MlProbabilities(
                    response.Probabilities.Sell,
                    response.Probabilities.Hold,
                    response.Probabilities.Buy),
                response.Confidence,
                response.ClosePrice,
                response.CandleOpenTime.ToDateTimeOffset(),
                response.Symbol,
                response.Interval,
                response.ModelId,
                response.ModelVersion,
                response.ModelTrainedAt.ToDateTimeOffset(),
                response.ProbabilityThreshold,
                response.InputDigestSha256,
                response.SellSemantics,
                response.Warning,
                response.ProcessingMilliseconds);
        }
        catch (RpcException exception)
        {
            logger.LogWarning(
                exception,
                "Python ML gRPC prediction failed with {StatusCode}",
                exception.StatusCode);
            throw new MlServiceException(
                exception.StatusCode.ToString(),
                exception.Status.Detail,
                exception);
        }
    }

    private DateTime Deadline() =>
        DateTime.UtcNow.AddSeconds(options.Value.DeadlineSeconds);
}
