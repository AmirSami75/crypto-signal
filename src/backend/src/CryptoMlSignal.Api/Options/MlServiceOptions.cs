namespace CryptoMlSignal.Api.Options;

public sealed class MlServiceOptions
{
    public const string SectionName = "MlService";

    public string Address { get; init; } = "http://localhost:50051";

    public int DeadlineSeconds { get; init; } = 10;

    public int MaxReceiveMessageMb { get; init; } = 4;
}
