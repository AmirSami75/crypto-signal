using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc.Authorization;
using Microsoft.OpenApi.Models;
using Swashbuckle.AspNetCore.SwaggerGen;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

public class AuthorizationOperationFilter : IOperationFilter
{
    public void Apply(OpenApiOperation operation, OperationFilterContext context)
    {
        var filters = context.ApiDescription.ActionDescriptor.FilterDescriptors;
        var metadta = context.ApiDescription.ActionDescriptor.EndpointMetadata;

        var hasAnonymous = filters.Any(p => p.Filter is AllowAnonymousFilter) || metadta.Any(p => p is AllowAnonymousAttribute);
        if (hasAnonymous) return;

        var hasAuthorize = filters.Any(p => p.Filter is AuthorizeFilter) || metadta.Any(p => p is AuthorizeAttribute);
        if (!hasAuthorize) return;

        operation.Responses.TryAdd("401", new OpenApiResponse { Description = "Unauthorized" });
        operation.Responses.TryAdd("403", new OpenApiResponse { Description = "Forbidden" });

        operation.Security.Add(new OpenApiSecurityRequirement
            {
                {
                    new OpenApiSecurityScheme
                    {
                          Reference = new OpenApiReference
                            {
                                Id = "Bearer",
                                Type = ReferenceType.SecurityScheme
                            }
                    },
                    Array.Empty<string>() //new[] { "readAccess", "writeAccess" }
                }
            });
    }

    //public void Apply(OpenApiOperation operation, OperationFilterContext context)
    //{
    //    var actionMetadata = context.ApiDescription.ActionDescriptor.EndpointMetadata;
    //    var isAuthorized = actionMetadata.Any(metadataItem => metadataItem is AuthorizeAttribute);
    //    var allowAnonymous = actionMetadata.Any(metadataItem => metadataItem is AllowAnonymousAttribute);
    //    if (!isAuthorized || allowAnonymous)
    //    {
    //        return;
    //    }

    //    operation.Parameters = new List<OpenApiParameter>();
    //    operation.Security = new List<OpenApiSecurityRequirement>
    //    {
    //        new OpenApiSecurityRequirement
    //        {
    //            {
    //                new OpenApiSecurityScheme
    //                {
    //                    Reference = new OpenApiReference
    //                    {
    //                        Id = "Bearer",
    //                        Type = ReferenceType.SecurityScheme
    //                    }
    //                },
    //                Array.Empty<string>()
    //            }
    //        }
    //    };
    //}
}
