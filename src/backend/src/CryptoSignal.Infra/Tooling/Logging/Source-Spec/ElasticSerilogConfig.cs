using System.Reflection;
using Elastic.Channels;
using Elastic.Ingest.Elasticsearch;
using Elastic.Ingest.Elasticsearch.DataStreams;
using Elastic.Serilog.Sinks;
using Elastic.Transport;
using Microsoft.Extensions.Configuration;
using CryptoSignal.Infra.Settings;
using CryptoSignal.Infra.Settings.Logging;
using CryptoSignal.Infra.Tooling.Logging.Abstract;
using Serilog;
using Serilog.Events;

namespace CryptoSignal.Infra.Tooling.Logging.Source_Spec;

public sealed class ElasticSerilogConfig(IConfiguration configuration) : BaseSerilogConfig(configuration)
{
    private readonly LoggingSettings _settings =
        configuration.GetSection("API_Settings:Logging").Get<LoggingSettings>() ?? new LoggingSettings();

    public override int Order => 200; // after console/file, before "exotic" sinks
    public override string Name => "Elastic"; // stable config key

    public override bool IsEnabled =>
        Configuration.GetValue<bool>("API_Settings:Logging:Sinks:Elastic:Enabled", true);

    public override LoggerConfiguration Configure(LoggerConfiguration loggerConfig)
    {
        var uris = ParseUris(_settings.Elastic.Url);
        if (uris.Length == 0)
            return loggerConfig;

        var appName = (Assembly.GetEntryAssembly()?.GetName().Name ?? "UnknownApp").ToLowerInvariant();
        var envName = (Environment.GetEnvironmentVariable("ASPNETCORE_ENVIRONMENT") ?? "Development")
            .ToLowerInvariant();

        // Optional: per-sink filter (keep global levels elsewhere)
        var sinkMinLevel = _settings.Elastic.MinimumLevel ?? LogEventLevel.Information;

        return loggerConfig.WriteTo.Async(a => a.Elasticsearch(
            uris,
            opts =>
            {
                opts.DataStream = new DataStreamName(
                    type: "logs",
                    dataSet: $"{appName}-logs",
                    @namespace: envName);

                opts.BootstrapMethod = BootstrapMethod.None;
                opts.MinimumLevel = sinkMinLevel;

                opts.ConfigureChannel = ch =>
                {
                    ch.BufferOptions = new BufferOptions
                    {
                        InboundBufferMaxSize = _settings.Elastic.InboundBufferMaxSize ?? 50_000,
                        OutboundBufferMaxSize = _settings.Elastic.OutboundBufferMaxSize ?? 2_000,
                        OutboundBufferMaxLifetime =
                            TimeSpan.FromSeconds(_settings.Elastic.OutboundBufferMaxLifetimeSeconds ?? 5),
                        ExportMaxConcurrency = _settings.Elastic.ExportMaxConcurrency ?? 4,
                        ExportMaxRetries = _settings.Elastic.ExportMaxRetries ?? int.MaxValue
                    };
                };
            },
            transport =>
            {
                // Prefer API key if present (common in prod)
                if (!string.IsNullOrWhiteSpace(_settings.Elastic.ApiKey))
                    transport.Authentication(new ApiKey(_settings.Elastic.ApiKey));
                else if (!string.IsNullOrWhiteSpace(_settings.Elastic.UserName) &&
                         !string.IsNullOrWhiteSpace(_settings.Elastic.Password))
                    transport.Authentication(new BasicAuthentication(_settings.Elastic.UserName,
                        _settings.Elastic.Password));

                transport.RequestTimeout(TimeSpan.FromSeconds(_settings.Elastic.RequestTimeoutSeconds ?? 10));

                if (_settings.Elastic.AllowInvalidTls)
                    transport.ServerCertificateValidationCallback((_, _, _, _) => true);
            }));
    }

    private static Uri[] ParseUris(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return [];

        var parts = raw.Split([';', ','], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        return parts
            .Select(p => Uri.TryCreate(p, UriKind.Absolute, out var u) ? u : null)
            .Where(u => u != null)
            .Cast<Uri>()
            .ToArray();
    }
}