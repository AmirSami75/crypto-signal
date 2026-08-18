using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.OpenApi.Models;
using Swashbuckle.AspNetCore.SwaggerGen;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

public class ScenarioDocumentFilter : IDocumentFilter
{
    private readonly string _currentScenario;

    public ScenarioDocumentFilter(string currentScenario)
    {
        _currentScenario = currentScenario;
    }

    public void Apply(OpenApiDocument swaggerDoc, DocumentFilterContext context)
    {
        var pathsToRemove = new List<string>();

        foreach (var apiDescription in context.ApiDescriptions)
        {
            if (apiDescription.RelativePath == null)
                continue;

            var actionDescriptor = apiDescription.ActionDescriptor as ControllerActionDescriptor;
        }

        // Remove paths
        foreach (var path in pathsToRemove.Distinct())
        {
            swaggerDoc.Paths.Remove(path);
        }

        // Remove controllers (tags) with no actions
        var usedTags = swaggerDoc.Paths
            .SelectMany(p => p.Value.Operations)
            .SelectMany(op => op.Value.Tags.Select(t => t.Name))
            .Distinct();

        swaggerDoc.Tags = swaggerDoc.Tags
            .Where(tag => usedTags.Contains(tag.Name))
            .ToList();

    }

}