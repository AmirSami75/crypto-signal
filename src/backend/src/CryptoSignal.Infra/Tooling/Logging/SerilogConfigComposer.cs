using System.Reflection;
using Microsoft.Extensions.Configuration;
using CryptoSignal.Infra.Tooling.Logging.Abstract;
using Serilog;
using Serilog.Events;

namespace CryptoSignal.Infra.Tooling.Logging;

public static class SerilogConfigComposer
{
    public static LoggerConfiguration Compose(
        IConfiguration configuration,
        params Assembly[]? scanAssemblies)
    {
        scanAssemblies ??= [Assembly.GetExecutingAssembly()];

        // Global baseline
        var loggerConfig = new LoggerConfiguration()
            .ReadFrom.Configuration(configuration)
            .Enrich.FromLogContext()
            .Enrich.WithMachineName()
            .Enrich.WithProcessId()
            .Enrich.WithThreadId()
            .Enrich.WithProperty("Application",
                configuration["ApplicationName"]
                ?? Assembly.GetEntryAssembly()?.GetName().Name
                ?? "UnknownApp");

        // Discover + build sink configs
        var configs = DiscoverConfigs(configuration, scanAssemblies);

        // Apply in order
        foreach (var cfg in configs.OrderBy(c => c.Order).ThenBy(c => c.Name))
        {
            if (!cfg.IsEnabled)
                continue;

            try
            {
                loggerConfig = cfg.Configure(loggerConfig);
            }
            catch (Exception ex)
            {
                // Never crash app due to logging; but don't hide it.
                // If you already have a bootstrap logger, use it here.
                Console.Error.WriteLine($"[SerilogConfigComposer] Failed to apply {cfg.Name}: {ex}");
            }
        }

        return loggerConfig;
    }

    private static IReadOnlyList<BaseSerilogConfig> DiscoverConfigs(
        IConfiguration configuration,
        Assembly[] assemblies)
    {
        var result = new List<BaseSerilogConfig>();

        foreach (var asm in assemblies.Distinct())
        {
            Type[] types;
            try { types = asm.GetTypes(); }
            catch (ReflectionTypeLoadException e) { types = e.Types.Where(t => t != null).Cast<Type>().ToArray(); }

            foreach (var t in types)
            {
                if (t is not { IsClass: true, IsAbstract: false }) continue;
                if (!typeof(BaseSerilogConfig).IsAssignableFrom(t)) continue;

                var instance = TryCreate(t, configuration);
                if (instance != null)
                    result.Add(instance);
            }
        }

        return result;
    }

    private static BaseSerilogConfig? TryCreate(Type type, IConfiguration configuration)
    {
        try
        {
            // Prefer ctor(IConfiguration)
            var ctor = type.GetConstructor([typeof(IConfiguration)]);
            if (ctor != null)
                return (BaseSerilogConfig)ctor.Invoke([configuration]);

            // Fallback to parameterless ctor
            ctor = type.GetConstructor(Type.EmptyTypes);
            if (ctor != null)
                return (BaseSerilogConfig)ctor.Invoke(null);

            Console.Error.WriteLine($"[SerilogConfigComposer] No suitable ctor found for {type.FullName}.");
            return null;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[SerilogConfigComposer] Failed to create {type.FullName}: {ex}");
            return null;
        }
    }
}
