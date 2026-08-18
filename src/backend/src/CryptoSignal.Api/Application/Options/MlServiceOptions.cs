namespace CryptoSignal.Api.Application.Options;

/// <summary>
/// gRPC channel configuration for the Python ML engine, bound from <c>MlService</c>.
/// Validated on start in <c>Program.cs</c>, so a malformed address fails the boot rather than the
/// first prediction request.
/// </summary>
public sealed class MlServiceOptions
{
    public const string SectionName = "MlService";

    /// <summary>Absolute address of the ML engine's gRPC endpoint.</summary>
    public string Address { get; init; } = "http://localhost:50051";

    /// <summary>Per-call deadline. Must be between 1 and 300.</summary>
    public int DeadlineSeconds { get; init; } = 10;

    /// <summary>Inbound message ceiling in MiB. Must be between 1 and 256.</summary>
    public int MaxReceiveMessageMb { get; init; } = 4;
}
