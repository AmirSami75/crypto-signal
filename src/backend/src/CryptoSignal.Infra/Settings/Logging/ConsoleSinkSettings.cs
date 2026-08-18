using Serilog.Events;

namespace CryptoSignal.Infra.Settings.Logging;

public class ConsoleSinkSettings
{
    public bool Enabled { get; set; } = true;

    public LogEventLevel MinimumLevel { get; set; } = LogEventLevel.Information;

    public bool UseAnsiTheme { get; set; } = true;

    public string OutputTemplate { get; set; } =
        "[{Timestamp:HH:mm:ss} {Level:u3}] {Message:lj}{NewLine}{Exception}";

    /// <summary>
    /// Namespace overrides specifically for console.
    /// </summary>
    public Dictionary<string, LogEventLevel> Overrides { get; set; } = new()
    {
        ["Microsoft"] = LogEventLevel.Warning,
        ["System"] = LogEventLevel.Warning
    };
}