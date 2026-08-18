using System.Text.Json;
using System.Text.Json.Serialization;
using CryptoSignal.Infra.Helpers.Serialization;

namespace CryptoSignal.Infra.Extensions.ExternalSvc;

/// <summary>
/// Centralized helpers for configuring System.Text.Json for Samat payloads.
/// </summary>
public static class ExternalServiceOptions
{
    /// <summary>
    /// Apply recommended Samat settings to an existing JsonSerializerOptions instance.
    /// </summary>
    public static JsonSerializerOptions Configure(JsonSerializerOptions options)
    {
        options.PropertyNameCaseInsensitive = true;
        options.ReadCommentHandling = JsonCommentHandling.Skip;
        options.AllowTrailingCommas = true;
        options.NumberHandling = JsonNumberHandling.AllowReadingFromString;
        // Register our tolerant converters once.
        options.Converters.Add(new StringifyConverter());
        options.Converters.Add(new IntOrStringToStringConverter());
        return options;
    }


    /// <summary>
    /// Create a fresh JsonSerializerOptions with the Samat defaults applied.
    /// </summary>
    public static JsonSerializerOptions Create()
        => Configure(new JsonSerializerOptions());
}