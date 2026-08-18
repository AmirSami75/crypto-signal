namespace CryptoSignal.Api.Application.Markers;

/// <summary>
/// Application service marker — implementations are auto-registered with a scoped lifetime.
/// </summary>
public interface IScopedSvcMarker;

/// <summary>
/// Application service marker — implementations are auto-registered with a singleton lifetime.
/// </summary>
public interface ISingletonSvcMarker;
