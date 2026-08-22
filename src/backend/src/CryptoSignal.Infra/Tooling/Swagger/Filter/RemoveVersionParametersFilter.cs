using Microsoft.OpenApi;
using Swashbuckle.AspNetCore.SwaggerGen;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

/// <summary>
/// Drops the route's <c>version</c> parameter from every operation. It is not a caller input:
/// <see cref="SetVersionInPathsFilter"/> substitutes the concrete version into the path, so leaving
/// the parameter in place would make the UI prompt for a value it has already filled in.
/// </summary>
public class RemoveVersionParametersFilter : IOperationFilter
{
    public void Apply(OpenApiOperation operation, OperationFilterContext context)
    {
        // Null for an operation that takes no parameters at all, which is most of them.
        if (operation.Parameters is null) return;

        // Iterated backwards over every match rather than SingleOrDefault: that overload throws as
        // soon as an action ends up with two parameters named "version", which would turn a cosmetic
        // cleanup into a failed document for the whole API.
        for (var i = operation.Parameters.Count - 1; i >= 0; i--)
        {
            if (operation.Parameters[i].Name == "version")
                operation.Parameters.RemoveAt(i);
        }
    }
}
