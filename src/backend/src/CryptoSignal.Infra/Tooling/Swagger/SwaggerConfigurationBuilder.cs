using CryptoSignal.Infra.Exceptions.Common;

namespace CryptoSignal.Infra.Tooling.Swagger;

public class SwaggerConfigurationBuilder
{
    private List<string> _xmlFilesName;
    private List<string> _versions;
    private string _apiName;

    public SwaggerConfigurationBuilder SetXMLFilesName(List<string> xmlFilesName)
    {
        _xmlFilesName = xmlFilesName;
        return this;
    }

    public SwaggerConfigurationBuilder SetVersions(List<string> versions)
    {
        _versions = versions;
        return this;
    }

    public SwaggerConfigurationBuilder SetApiName(string apiName)
    {
        _apiName = apiName;
        return this;
    }

    public SwaggerConfiguration Build()
    {
        // Validate required properties
        if (_xmlFilesName == null || !_xmlFilesName.Any())
            throw new LogicException("XmlFilesName is required and cannot be null or empty.");

        if (_versions == null || !_versions.Any())
            throw new LogicException("Versions are required and cannot be null or empty.");

        if (string.IsNullOrEmpty(_apiName))
            throw new LogicException("ApiName is required and cannot be null or empty.");

        return new SwaggerConfiguration(
            _xmlFilesName,
            _versions,
            _apiName
        );
    }
}
