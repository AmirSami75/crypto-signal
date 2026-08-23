using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc.Authorization;
using Microsoft.OpenApi;
using Swashbuckle.AspNetCore.SwaggerGen;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

/// <summary>
/// Advertises the bearer requirement and the 401/403 responses on operations that actually enforce
/// authorization, so the Swagger UI sends the token only where it is needed.
/// </summary>
public class AuthorizationOperationFilter : IOperationFilter
{
    public void Apply(OpenApiOperation operation, OperationFilterContext context)
    {
        var filters = context.ApiDescription.ActionDescriptor.FilterDescriptors;
        var metadata = context.ApiDescription.ActionDescriptor.EndpointMetadata;

        // Both collections are checked because the two mechanisms are not interchangeable:
        // [Authorize] on a controller arrives as a filter descriptor, while endpoint-routing
        // metadata carries the attribute itself.
        var hasAnonymous = filters.Any(p => p.Filter is AllowAnonymousFilter)
                           || metadata.Any(p => p is AllowAnonymousAttribute);
        if (hasAnonymous) return;

        var hasAuthorize = filters.Any(p => p.Filter is AuthorizeFilter)
                           || metadata.Any(p => p is AuthorizeAttribute);
        if (!hasAuthorize) return;

        // Both collections are nullable in Microsoft.OpenApi 2.x and are left unset for an operation
        // that declares neither responses nor security, so they are materialised before being added
        // to rather than dereferenced.
        operation.Responses ??= new OpenApiResponses();
        operation.Responses.TryAdd("401", new OpenApiResponse { Description = "Unauthorized" });
        operation.Responses.TryAdd("403", new OpenApiResponse { Description = "Forbidden" });

        // Microsoft.OpenApi 2.x models a reference as its own type rather than a Reference property
        // on the scheme, so the requirement points at the "Bearer" definition registered in
        // AddSwagger by id. The empty scope list is required by the spec for non-OAuth2 schemes.
        //
        // `context.Document` is the load-bearing argument, and leaving it off is silent: the reference
        // constructs happily, the operation reports a requirement in memory, and the writer then drops
        // it. OpenApiSecurityRequirement.SerializeInternal only emits a key whose reference can be
        // resolved — `Target is not null`, or an id that is present in
        // `Reference.HostDocument.Components.SecuritySchemes` — and a reference built without a host
        // document satisfies neither. Every protected operation serialises as `"security": [{}]`,
        // which per the spec is an *empty* requirement, i.e. anonymous. The Swagger UI reads that as
        // "no auth here", shows no padlock, and never attaches the token however many times you paste
        // it into the Authorize dialog. The document is passed by reference and resolution happens at
        // write time, so it does not matter that Components is still being filled in right now.
        operation.Security ??= [];
        operation.Security.Add(new OpenApiSecurityRequirement
        {
            [new OpenApiSecuritySchemeReference("Bearer", context.Document)] = []
        });
    }
}
