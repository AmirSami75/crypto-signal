namespace CryptoSignal.Infra.Tooling.Swagger;

public class SwaggerConfiguration
{
    public IReadOnlyList<string> XmlFilesName { get; }
    public IReadOnlyList<string> Versions { get; }
    public string ApiName { get; set; }
    public string ScenarioName { get; }
    public bool IsScenarioNameSet => !string.IsNullOrEmpty(ScenarioName);

    internal SwaggerConfiguration(List<string> xmlFilesName, List<string> versions, string apiName)
    {
        XmlFilesName = xmlFilesName;
        Versions = versions;
        ApiName = apiName;
    }
}
