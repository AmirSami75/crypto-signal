using Serilog.Events;

namespace CryptoSignal.Infra.Settings.Logging;

public sealed class FileSinkSettings
{
    public bool Enabled { get; set; } = true;

    /// <summary>
    /// Root directory for logs. If empty, BaseDirectory is used.
    /// </summary>
    public string? Root { get; set; }

    public bool UseJson { get; set; } = false;

    public long FileSizeLimitBytes { get; set; } = 20_000_000;
    public int RetainedFileCountLimit { get; set; } = 10;

    /// <summary>
    /// Base minimum level for file sink.
    /// Fine-grained routing is still handled in FileSerilogConfig.
    /// </summary>
    public LogEventLevel MinimumLevel { get; set; } = LogEventLevel.Information;

    /// <summary>
    /// Output template for text logs.
    /// </summary>
    public string OutputTemplate { get; set; } =
        "[{Timestamp:yyyy-MM-dd HH:mm:ss.ff zzz}] [{Level:u3}] {Message:lj}{NewLine}{Exception}";
}