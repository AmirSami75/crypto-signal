namespace CryptoSignal.Api.Contracts;

/// <summary>Links a client can follow from the API index.</summary>
public sealed record ApiIndexLinks(
    string Platform,
    string Login,
    string Users,
    string Roles,
    string Permissions,
    string MlCapabilities,
    string MlModel,
    string MlSignal,
    string Swagger,
    string LiveHealth,
    string ReadyHealth);

/// <summary>API index response.</summary>
public sealed record ApiIndex(
    string Name,
    string Version,
    string Orchestrator,
    ApiIndexLinks Links);

/// <summary>Describes how the running platform is composed and which trading mode it is in.</summary>
public sealed record PlatformInfo(
    string Backend,
    string MachineLearning,
    string Dashboard,
    string Database,
    string OperatingMode,
    string ExecutionPolicy);

/// <summary>Liveness/readiness payload. Deliberately outside the ApiResult envelope so container
/// orchestrators and load balancers can parse it without knowing this API's conventions.</summary>
public sealed record HealthReport(
    string Service,
    string Status,
    DateTimeOffset Timestamp,
    IReadOnlyList<DependencyHealth>? Dependencies = null);
