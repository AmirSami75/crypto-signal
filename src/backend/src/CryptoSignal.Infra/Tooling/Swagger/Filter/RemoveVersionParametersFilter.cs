using Microsoft.OpenApi.Models;
using Swashbuckle.AspNetCore.SwaggerGen;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

public class RemoveVersionParametersFilter : IOperationFilter
{
    public void Apply(OpenApiOperation operation, OperationFilterContext context)
    {
        // Remove version parameter from all Operations
        var versionParameter = operation.Parameters.SingleOrDefault(p => p.Name == "version");
        if (versionParameter != null)
            operation.Parameters.Remove(versionParameter);
    }
}

