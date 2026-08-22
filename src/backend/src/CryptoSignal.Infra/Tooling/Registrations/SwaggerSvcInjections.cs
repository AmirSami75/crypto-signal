using System.Reflection;
using Asp.Versioning;
using Microsoft.Extensions.DependencyInjection;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Tooling.Swagger;
using CryptoSignal.Infra.Tooling.Swagger.Filter;
using Microsoft.OpenApi;
using Swashbuckle.AspNetCore.Filters;
using Swashbuckle.AspNetCore.SwaggerGen;
using Path = System.IO.Path;

namespace CryptoSignal.Infra.Tooling.Registrations;

public static class SwaggerSvcInjections
{
    /// <summary>
    /// Registers Swagger generation: XML comments, one document per configured version, JWT bearer
    /// security, and the operation/document filters that normalise summaries and version routes.
    /// </summary>
    public static void AddSwagger(this IServiceCollection services, SwaggerConfiguration swaggerConfiguration)
    {
        Assert.NotNull(services, nameof(services));
        Assert.NotNull(swaggerConfiguration, nameof(swaggerConfiguration));

        //Add services to use Example Filters in swagger
        services.AddSwaggerExamples();

        //Add services and configuration to use swagger
        services.AddSwaggerGen(options =>
        {
            foreach (var xmlFileName in swaggerConfiguration.XmlFilesName)
            {
                var xmlDocPath = Path.Combine(AppContext.BaseDirectory, xmlFileName);

                // Skipped rather than thrown on. IncludeXmlComments opens the file eagerly, so a
                // single missing file takes the whole process down at startup — and the assemblies
                // listed here are referenced projects whose GenerateDocumentationFile setting this
                // library cannot control. A missing file costs documentation, not availability.
                if (!File.Exists(xmlDocPath)) continue;

                options.IncludeXmlComments(xmlDocPath, includeControllerXmlComments: true);
            }

            //show controller XML comments like summary
            options.EnableAnnotations();

            foreach (var version in swaggerConfiguration.Versions)
            {
                // Version has to be the document's own version, not a constant. SetVersionInPathsFilter
                // substitutes Info.Version into the "v{version}" route placeholder, so hardcoding it
                // would point every document's paths at the same version.
                options.SwaggerDoc(version, new OpenApiInfo
                {
                    Version = version,
                    Title = swaggerConfiguration.ApiName
                });
            }

            #region Filters

            //Enable to use [SwaggerRequestExample] & [SwaggerResponseExample]
            options.ExampleFilters();

            //Set summary of action if not already set
            options.OperationFilter<ApplySummariesOperationFilter>();

            #region Add Jwt Authentication

            //Add Lockout icon on top of swagger ui page to authenticate

            var securityScheme = new OpenApiSecurityScheme()
            {
                Description = "Enter JWT Token Without Bearer String ...",
                Name = "Authorization",
                In = ParameterLocation.Header,
                Type = SecuritySchemeType.Http,
                Scheme = "bearer",
                BearerFormat = "JWT" // Optional
            };
            options.AddSecurityDefinition("Bearer", securityScheme);
            options.OperationFilter<AuthorizationOperationFilter>();

            #endregion

            #region Versioning

            // Remove version parameter from all Operations
            options.OperationFilter<RemoveVersionParametersFilter>();

            //set version "api/v{version}/[controller]" from current swagger doc verion
            options.DocumentFilter<SetVersionInPathsFilter>();

            //Seperate and categorize end-points by doc version
            options.DocInclusionPredicate((docName, apiDesc) =>
            {
                if (!apiDesc.TryGetMethodInfo(out MethodInfo methodInfo)) return false;

                // A method reached through a non-controller endpoint has no declaring type, so there
                // is nothing to read an ApiVersion from — exclude it instead of dereferencing null.
                var declaringType = methodInfo.DeclaringType;
                if (declaringType is null) return false;

                return declaringType
                    .GetCustomAttributes<ApiVersionAttribute>(inherit: true)
                    .SelectMany(attr => attr.Versions)
                    .Any(v => $"v{v}" == docName);
            });

            #endregion

            //If use FluentValidation then must be use this package to show validation in swagger (MicroElements.Swashbuckle.FluentValidation)
            //options.AddFluentValidationRules();

            #endregion
        });
    }
}
