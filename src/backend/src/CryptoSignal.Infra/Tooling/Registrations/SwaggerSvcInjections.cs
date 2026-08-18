using System.Reflection;
using Asp.Versioning;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.OpenApi.Models;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Tooling.Swagger;
using CryptoSignal.Infra.Tooling.Swagger.Filter;
using Swashbuckle.AspNetCore.Filters;
using Swashbuckle.AspNetCore.SwaggerGen;
using Path = System.IO.Path;

namespace CryptoSignal.Infra.Tooling.Registrations;

public static class SwaggerSvcInjections
{
    public static void AddSwagger(this IServiceCollection services, SwaggerConfiguration swaggerConfiguration)
    {
        Assert.NotNull(services, nameof(services));

        //Add services to use Example Filters in swagger
        services.AddSwaggerExamples();

        //Add services and configuration to use swagger
        services.AddSwaggerGen(options =>
        {
            foreach (var xmlFileName in swaggerConfiguration.XmlFilesName)
            {
                var xmlDocPath = Path.Combine(AppContext.BaseDirectory, xmlFileName);
                options.IncludeXmlComments(xmlDocPath, true);
            }

            //show controller XML comments like summary
            options.EnableAnnotations();

            swaggerConfiguration.ApiName = string.IsNullOrEmpty(swaggerConfiguration.ApiName)
                ? "Api"
                : swaggerConfiguration.ApiName;
            foreach (var version in swaggerConfiguration.Versions)
            {
                options.SwaggerDoc(version,
                    new OpenApiInfo { Version = "v1", Title = $"{swaggerConfiguration.ApiName}" });
            }

            #region Filters

            //Enable to use [SwaggerRequestExample] & [SwaggerResponseExample]
            options.ExampleFilters();

            //Set summary of action if not already set
            options.OperationFilter<ApplySummariesOperationFilter>();

            //Set correct apies that match with Scenario
            if (swaggerConfiguration.IsScenarioNameSet)
                options.DocumentFilter<ScenarioDocumentFilter>(swaggerConfiguration.ScenarioName);

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

                var versions = methodInfo.DeclaringType
                    .GetCustomAttributes<ApiVersionAttribute>(true)
                    .SelectMany(attr => attr.Versions);

                return versions.Any(v => $"v{v}" == docName);
            });

            #endregion

            //If use FluentValidation then must be use this package to show validation in swagger (MicroElements.Swashbuckle.FluentValidation)
            //options.AddFluentValidationRules();

            #endregion
        });
    }
}