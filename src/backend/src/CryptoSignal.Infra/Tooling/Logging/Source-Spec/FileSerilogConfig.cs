using System.Reflection;
using Microsoft.Extensions.Configuration;
using CryptoSignal.Infra.Tooling.Logging.Abstract;
using Serilog;
using Serilog.Events;
using Serilog.Filters;
using Serilog.Formatting.Json; 
using Path = System.IO.Path;

namespace CryptoSignal.Infra.Tooling.Logging.Source_Spec;

public sealed class FileSerilogConfig : BaseSerilogConfig
{
    public FileSerilogConfig(IConfiguration cfg) : base(cfg) { }

    public override int Order => 100;     // usually file before elastic
    public override string Name => "File";

    public override bool IsEnabled =>
        Configuration.GetValue<bool>("API_Settings:Logging:Sinks:File:Enabled", true);

    public override LoggerConfiguration Configure(LoggerConfiguration loggerConfig)
    {
        // ----- Settings (configurable, defaults if missing) -----
        var appName = (Configuration["ApplicationName"]
                       ?? Assembly.GetEntryAssembly()?.GetName().Name
                       ?? "UnknownApp");

        var envName = (Environment.GetEnvironmentVariable("ASPNETCORE_ENVIRONMENT")
                       ?? "Development");
        
        var root = Configuration["API_Settings:Logging:File:Root"];
        if (string.IsNullOrWhiteSpace(root))
        {
            // fallback: base directory (ok in containers, but sometimes read-only)
            root = AppDomain.CurrentDomain.BaseDirectory;
        }

        var logsRoot = Path.Combine(root, "logs", appName, envName);
        Directory.CreateDirectory(logsRoot);

        var fileSizeLimit = Configuration.GetValue<long?>("API_Settings:Logging:File:FileSizeLimitBytes") ?? 20_000_000;
        var retainedFiles = Configuration.GetValue<int?>("API_Settings:Logging:File:RetainedFileCountLimit") ?? 10;

        var useJson = Configuration.GetValue<bool>("API_Settings:Logging:File:UseJson", false);

        // Templates (text mode)
        const string infoTemplate =
            "[{Timestamp:yyyy-MM-dd HH:mm:ss.ff zzz}] [{Level:u3}] {Message:lj}{NewLine}";
        const string errorTemplate =
            "[{Timestamp:yyyy-MM-dd HH:mm:ss.ff zzz}] [{Level:u3}] {Message:lj}{NewLine}{Exception}{NewLine}";

        // ----- Paths -----
        var infoPath = Path.Combine(logsRoot, "info-.log");
        var warnPath = Path.Combine(logsRoot, "warn-.log");
        var errorPath = Path.Combine(logsRoot, "error-.log");
        var exceptionsPath = Path.Combine(logsRoot, "exceptions-.log");

        // ----- Writers (helper avoids repetition) -----
        LoggerConfiguration AddRollingFile(
            LoggerConfiguration cfg,
            string path,
            LogEventLevel restrictedToMinimumLevel,
            string outputTemplate,
            Func<LogEvent, bool>? include = null)
        {
            return cfg.WriteTo.Logger(lc =>
            {
                if (include != null)
                    lc.Filter.ByIncludingOnly(include);

                if (useJson)
                {
                    lc.WriteTo.Async(a => a.File(
                        formatter: new JsonFormatter(renderMessage: true),
                        path: path,
                        rollingInterval: RollingInterval.Day,
                        fileSizeLimitBytes: fileSizeLimit,
                        retainedFileCountLimit: retainedFiles,
                        restrictedToMinimumLevel: restrictedToMinimumLevel
                    ));

                    return; // <-- important: end the Action
                }

                lc.WriteTo.Async(a => a.File(
                    path: path,
                    rollingInterval: RollingInterval.Day,
                    fileSizeLimitBytes: fileSizeLimit,
                    retainedFileCountLimit: retainedFiles,
                    restrictedToMinimumLevel: restrictedToMinimumLevel,
                    outputTemplate: outputTemplate
                ));
            });
        }

        // ----- Routing rules -----
        // 1) Info without exception
        loggerConfig = AddRollingFile(
            loggerConfig,
            infoPath,
            LogEventLevel.Information,
            infoTemplate,
            include: e => e.Level == LogEventLevel.Information && e.Exception is null);

        // 2) Warning without exception
        loggerConfig = AddRollingFile(
            loggerConfig,
            warnPath,
            LogEventLevel.Warning,
            infoTemplate,
            include: e => e.Level == LogEventLevel.Warning && e.Exception is null);

        // 3) Error/Fatal (whether or not exception)
        loggerConfig = AddRollingFile(
            loggerConfig,
            errorPath,
            LogEventLevel.Error,
            errorTemplate,
            include: e => e.Level is LogEventLevel.Error or LogEventLevel.Fatal);

        // 4) Anything with exception (explicit “exceptions channel”)
        // Note: this intentionally overlaps with errorPath for Error+Exception.
        // If you want "exceptions only for non-error levels", change the predicate.
        loggerConfig = AddRollingFile(
            loggerConfig,
            exceptionsPath,
            LogEventLevel.Verbose,
            errorTemplate,
            include: e => e.Exception is not null);

        return loggerConfig;
    }
}
