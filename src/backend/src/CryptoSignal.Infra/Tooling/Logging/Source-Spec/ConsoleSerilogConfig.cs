using Microsoft.Extensions.Configuration;
using CryptoSignal.Infra.Tooling.Logging.Abstract;
using Serilog;
using Serilog.Events;
using Serilog.Sinks.SystemConsole.Themes;

namespace CryptoSignal.Infra.Tooling.Logging.Source_Spec;

public sealed class ConsoleSerilogConfig : BaseSerilogConfig
{
    public ConsoleSerilogConfig(IConfiguration cfg) : base(cfg) { }

    public override int Order => 10;          // console early
    public override string Name => "Console"; // stable key: API_Settings:Logging:Sinks:Console

    public override bool IsEnabled =>
        Configuration.GetValue<bool>("API_Settings:Logging:Sinks:Console:Enabled", true);

    public override LoggerConfiguration Configure(LoggerConfiguration loggerConfig)
    {
        var minLevel = ParseLevel(
            Configuration["API_Settings:Logging:Sinks:Console:MinimumLevel"],
            defaultLevel: LogEventLevel.Information);

        var outputTemplate =
            Configuration["API_Settings:Logging:Sinks:Console:OutputTemplate"]
            ?? "[{Timestamp:HH:mm:ss} {Level:u3}] {Message:lj}{NewLine}{Exception}";

        var useAnsiTheme =
            Configuration.GetValue<bool>("API_Settings:Logging:Sinks:Console:UseAnsiTheme", true);

        // optional: quiet noisy namespaces on console
        var overrideMicrosoft =
            ParseLevel(Configuration["API_Settings:Logging:Sinks:Console:Override:Microsoft"], LogEventLevel.Warning);
        var overrideSystem =
            ParseLevel(Configuration["API_Settings:Logging:Sinks:Console:Override:System"], LogEventLevel.Warning);

        loggerConfig = loggerConfig
            .MinimumLevel.Override("Microsoft", overrideMicrosoft)
            .MinimumLevel.Override("System", overrideSystem);

        return loggerConfig.WriteTo.Console(
            restrictedToMinimumLevel: minLevel,
            outputTemplate: outputTemplate,
            theme: useAnsiTheme ? AnsiConsoleTheme.Code : SystemConsoleTheme.Literate);
    }

    private static LogEventLevel ParseLevel(string? value, LogEventLevel defaultLevel)
        => Enum.TryParse<LogEventLevel>(value, ignoreCase: true, out var lvl) ? lvl : defaultLevel;
}
