namespace CryptoSignal.Infra.Tooling.Swagger;

/// <summary>
/// Validated input for <c>AddSwagger</c>. Instances only come from
/// <see cref="SwaggerConfigurationBuilder"/>, which rejects empty values, so every property here is
/// guaranteed to be populated and none of them are mutated afterwards.
/// </summary>
public class SwaggerConfiguration
{
    /// <summary>
    /// XML documentation file names, each resolved against <see cref="AppContext.BaseDirectory"/>.
    /// One entry per assembly whose comments should reach the document — inherited base-controller
    /// documentation only appears if the declaring assembly's file is listed.
    /// </summary>
    public IReadOnlyList<string> XmlFilesName { get; }

    /// <summary>
    /// Document names to emit, one Swagger document per entry. These are matched against the
    /// <c>ApiVersion</c> attributes on controllers, so they carry the <c>v</c> prefix: <c>v1</c>.
    /// </summary>
    public IReadOnlyList<string> Versions { get; }

    /// <summary>Title shown in the Swagger UI.</summary>
    public string ApiName { get; }

    internal SwaggerConfiguration(List<string> xmlFilesName, List<string> versions, string apiName)
    {
        XmlFilesName = xmlFilesName;
        Versions = versions;
        ApiName = apiName;
    }
}
