using CryptoSignal.Infra.Exceptions.Common;

namespace CryptoSignal.Infra.Tooling.Swagger;

/// <summary>
/// Fluent builder for <see cref="SwaggerConfiguration"/>. Nothing is validated until
/// <see cref="Build"/> is called, which is why the backing fields are nullable: an unset value is a
/// legitimate intermediate state that <see cref="Build"/> turns into a named error.
/// </summary>
public class SwaggerConfigurationBuilder
{
    private List<string>? _xmlFilesName;
    private List<string>? _versions;
    private string? _apiName;

    /// <summary>Sets the XML documentation files to merge into the document.</summary>
    public SwaggerConfigurationBuilder SetXMLFilesName(List<string> xmlFilesName)
    {
        _xmlFilesName = xmlFilesName;
        return this;
    }

    /// <summary>Sets the document names to emit — for example <c>["v1"]</c>.</summary>
    public SwaggerConfigurationBuilder SetVersions(List<string> versions)
    {
        _versions = versions;
        return this;
    }

    /// <summary>Sets the title shown in the Swagger UI.</summary>
    public SwaggerConfigurationBuilder SetApiName(string apiName)
    {
        _apiName = apiName;
        return this;
    }

    /// <summary>
    /// Validates every value and produces the configuration. Throws <see cref="LogicException"/>
    /// naming the missing value rather than deferring to a null reference during document
    /// generation, where the failure would surface as an unrelated Swagger error.
    /// </summary>
    public SwaggerConfiguration Build()
    {
        if (_xmlFilesName is null || _xmlFilesName.Count == 0)
            throw new LogicException("XmlFilesName is required and cannot be null or empty.");

        if (_versions is null || _versions.Count == 0)
            throw new LogicException("Versions are required and cannot be null or empty.");

        if (string.IsNullOrWhiteSpace(_apiName))
            throw new LogicException("ApiName is required and cannot be null or empty.");

        return new SwaggerConfiguration(
            _xmlFilesName,
            _versions,
            _apiName
        );
    }
}
