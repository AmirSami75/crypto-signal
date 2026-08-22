using Microsoft.OpenApi;
using Swashbuckle.AspNetCore.SwaggerGen;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

/// <summary>
/// Substitutes the document's own version into the <c>api/v{version}/[controller]</c> route
/// placeholder, so the paths shown in the UI are the paths a caller can actually request.
/// </summary>
public class SetVersionInPathsFilter : IDocumentFilter
{
    public void Apply(OpenApiDocument swaggerDoc, DocumentFilterContext context)
    {
        // Without a version there is nothing to substitute, and replacing the placeholder with an
        // empty string would emit "api//user" — worse than leaving the template visible.
        var version = swaggerDoc.Info?.Version;
        if (string.IsNullOrEmpty(version)) return;

        var updatedPaths = new OpenApiPaths();

        foreach (var entry in swaggerDoc.Paths)
        {
            updatedPaths.Add(entry.Key.Replace("v{version}", version), entry.Value);
        }

        swaggerDoc.Paths = updatedPaths;
    }
}
