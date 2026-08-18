using System;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace CryptoSignal.Infra.Helpers.Serialization;

/// <summary>
/// Converts JSON scalars (string/number/bool/null) to string without changing their textual meaning.
/// - Strings: returns the unescaped .NET string.
/// - Numbers: returns the exact numeric literal (preserves exponent/trailing zeros).
/// - Booleans: "true"/"false".
/// - Null: null.
/// Throws on non-scalar tokens (object/array/property name).
/// </summary>
public sealed class StringifyConverter : JsonConverter<string?>
{
    public override string? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        => reader.TokenType switch
        {
            JsonTokenType.String => reader.GetString(),
            JsonTokenType.Number => Decode(reader.ValueSpan),
            JsonTokenType.True   => "true",
            JsonTokenType.False  => "false",
            JsonTokenType.Null   => null,
            _ => throw new JsonException(
                $"Expected string/number/bool/null but found {reader.TokenType} at byte position {reader.TokenStartIndex}.")
        };

    public override void Write(Utf8JsonWriter writer, string? value, JsonSerializerOptions options)
    {
        if (value is null) { writer.WriteNullValue(); return; }
        writer.WriteStringValue(value);
    }

    private static string Decode(ReadOnlySpan<byte> utf8) =>
        Encoding.UTF8.GetString(utf8);
}