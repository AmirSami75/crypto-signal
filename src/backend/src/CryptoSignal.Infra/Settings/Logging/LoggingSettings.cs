using Serilog.Events;

namespace CryptoSignal.Infra.Settings.Logging;

/// <summary>
/// Root logging configuration.
/// Bound from: API_Settings:Logging
/// </summary>
public sealed class LoggingSettings
{
    // ===============================
    // Sink toggles
    // ===============================
    public SinkToggleSettings Sinks { get; set; } = new();
    // ===============================
    // Individual sink settings
    // ===============================
    public ConsoleSinkSettings Console { get; set; } = new();
    public FileSinkSettings File { get; set; } = new();
    public ElasticSinkSettings Elastic { get; set; } = new();
    public EfCommandTracerSettings EfCommandTracer { get; set; } = new();
}