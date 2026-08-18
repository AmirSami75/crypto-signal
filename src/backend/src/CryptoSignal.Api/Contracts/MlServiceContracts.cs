namespace CryptoSignal.Api.Contracts;

public sealed record MlServiceCapabilities(
    string Service,
    string ServiceVersion,
    string ProtocolVersion,
    string[] Capabilities,
    string[] SupportedOperations,
    bool ModelReady,
    uint MinimumCandles,
    uint MaximumCandles);

public sealed record MlModelInfo(
    bool Ready,
    string ModelId,
    string ModelVersion,
    string ProjectVersion,
    string Symbol,
    string Interval,
    DateTimeOffset TrainedAt,
    uint FeatureCount,
    double ProbabilityThreshold,
    string SellSemantics);

public sealed record MlCandle(
    DateTimeOffset OpenTime,
    double Open,
    double High,
    double Low,
    double Close,
    double Volume);

public sealed record MlPredictionRequest(
    string Symbol,
    string Interval,
    IReadOnlyList<MlCandle> Candles,
    string? ExpectedModelVersion = null,
    string? RequestId = null);

public sealed record MlProbabilities(double Sell, double Hold, double Buy);

public sealed record MlPrediction(
    string RequestId,
    string Signal,
    int NumericSignal,
    MlProbabilities Probabilities,
    double Confidence,
    double ClosePrice,
    DateTimeOffset CandleOpenTime,
    string Symbol,
    string Interval,
    string ModelId,
    string ModelVersion,
    DateTimeOffset ModelTrainedAt,
    double ProbabilityThreshold,
    string InputDigestSha256,
    string SellSemantics,
    string Warning,
    double ProcessingMilliseconds);

public sealed record DependencyHealth(
    string Name,
    string Status,
    string? Detail = null);

public sealed class MlServiceException(
    string errorCode,
    string message,
    Exception? innerException = null) : Exception(message, innerException)
{
    public string ErrorCode { get; } = errorCode;
}
