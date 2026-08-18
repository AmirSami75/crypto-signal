using Serilog.Events;

namespace CryptoSignal.Infra.Settings.Logging;

public sealed class ElasticSinkSettings
{
    public bool Enabled { get; set; } = true;

    /// <summary>
    /// One or more URLs separated by ';' or ','.
    /// </summary>
    public string? Url { get; set; }

    // ---- Authentication ----
    public string? UserName { get; set; }
    public string? Password { get; set; }
    public string? ApiKey { get; set; }

    // ---- Transport ----
    public int? RequestTimeoutSeconds { get; set; } = 10;
    public bool AllowInvalidTls { get; set; } = false;

    // ---- Levels ----
    public LogEventLevel? MinimumLevel { get; set; } = LogEventLevel.Information;

    // ---- Channel / buffering ----
    public int? InboundBufferMaxSize { get; set; } = 50_000;
    public int? OutboundBufferMaxSize { get; set; } = 2_000;
    public int? OutboundBufferMaxLifetimeSeconds { get; set; } = 5;
    public int? ExportMaxConcurrency { get; set; } = 4;
    public int? ExportMaxRetries { get; set; } = int.MaxValue;
}