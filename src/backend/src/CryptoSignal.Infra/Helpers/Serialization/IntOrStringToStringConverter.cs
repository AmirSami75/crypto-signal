using System;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace CryptoSignal.Infra.Helpers.Serialization;

/// <summary>
/// Reads an int or a string token and always produces a string (preserves leading zeros like "01069").
/// </summary>
public sealed class IntOrStringToStringConverter : JsonConverter<string?>
{
    public override string? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        => reader.TokenType switch
        {
            JsonTokenType.String => reader.GetString(),
            JsonTokenType.Number => reader.TryGetInt64(out var n)
                ? n.ToString(CultureInfo.InvariantCulture)
                : reader.GetDouble().ToString("G17", CultureInfo.InvariantCulture), // keep precision
            JsonTokenType.Null   => null,
            // Anything else means the JSON did not contain a scalar string/number here.
            _ => throw new JsonException(
                $"Expected string or number but found {reader.TokenType} at byte position {reader.TokenStartIndex}.")
        };

    public override void Write(Utf8JsonWriter writer, string? value, JsonSerializerOptions options)
    {
        if (value is null) { writer.WriteNullValue(); return; }
        writer.WriteStringValue(value);
    }
}