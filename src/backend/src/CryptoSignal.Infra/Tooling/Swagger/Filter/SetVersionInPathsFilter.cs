using Microsoft.OpenApi.Models;
using Swashbuckle.AspNetCore.SwaggerGen;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

public class SetVersionInPathsFilter : IDocumentFilter
{
    public void Apply(OpenApiDocument swaggerDoc, DocumentFilterContext context)
    {
        var updatedPaths = new OpenApiPaths();

        foreach (var entry in swaggerDoc.Paths)
        {
            updatedPaths.Add(
                entry.Key.Replace("v{version}", swaggerDoc.Info.Version),
                entry.Value);
        }

        swaggerDoc.Paths = updatedPaths;
    }
}

