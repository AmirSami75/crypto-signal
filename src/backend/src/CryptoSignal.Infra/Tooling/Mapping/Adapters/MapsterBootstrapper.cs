using System.Reflection;
using Mapster;

namespace CryptoSignal.Infra.Tooling.Mapping.Adapters;

public static class MapsterBootstrapper
{
    public static TypeAdapterConfig Bootstrap(params Assembly[] assemblies)
    {
        var config = TypeAdapterConfig.GlobalSettings;

        // Scan all IRegister/IMapRegister profiles in your assemblies
        if (assemblies is { Length: > 0 })
            config.Scan(assemblies);

        // Sensible defaults
        config.Default
            .NameMatchingStrategy(NameMatchingStrategy.Flexible)
            .ShallowCopyForSameType(false)
            .IgnoreNullValues(false);

        return config;
    }
}