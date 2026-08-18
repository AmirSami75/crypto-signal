using Microsoft.AspNetCore.Builder;
using CryptoSignal.Infra.Exceptions.Common;
using Swashbuckle.AspNetCore.SwaggerUI;

namespace CryptoSignal.Infra.Middlewares;

public static class SwaggerCfgs
{
    public static void UseSwaggerAndUI(this IApplicationBuilder app, List<string> versions)
    {
        Assert.NotNull(app, nameof(app));

        //Swagger middleware for generate "Open API Documentation" in swagger.json
        app.UseSwagger(options =>
        {
            //options.RouteTemplate = "api-docs/{documentName}/swagger.json";
        });

        //Swagger middleware for generate UI from swagger.json
        app.UseSwaggerUI(options =>
        {
            foreach (var version in versions)
            {
                options.SwaggerEndpoint($"/swagger/{version}/swagger.json", $"{version.ToUpper()} Docs");
            }

            #region Customizing
            //// Display
            //options.DefaultModelExpandDepth(2);
            //options.DefaultModelRendering(ModelRendering.Model);
            //options.DefaultModelsExpandDepth(-1);
            //options.DisplayOperationId();
            //options.DisplayRequestDuration();
            options.DocExpansion(DocExpansion.None);
            // options.EnableDeepLinking();
            options.EnableFilter();
            options.MaxDisplayedTags(50);
            //  options.ShowExtensions();

            //// Network
            options.EnableValidator();
            //   options.SupportedSubmitMethods(SubmitMethod.Get);

            //// Other
            //options.DocumentTitle = "CustomUIConfig";
            //options.InjectStylesheet("/ext/custom-stylesheet.css");
            //options.InjectJavascript("/ext/custom-javascript.js");
            //options.RoutePrefix = "api-docs";
            #endregion
        });

        //ReDoc UI middleware. ReDoc UI is an alternative to swagger-ui
        app.UseReDoc(options =>
        {
            foreach (var version in versions)
            {
                options.SpecUrl($"/swagger/{version}/swagger.json");
            }

            #region Customizing
            //By default, the ReDoc UI will be exposed at "/api-docs"
            //options.RoutePrefix = "docs";
            //options.DocumentTitle = "API Docs";

            options.EnableUntrustedSpec();
            options.ScrollYOffset(10);
            options.HideHostname();
            options.HideDownloadButton();
            options.ExpandResponses("200,201");
            options.RequiredPropsFirst();
            options.NoAutoAuth();
            options.PathInMiddlePanel();
            options.HideLoading();
            options.NativeScrollbars();
            options.DisableSearch();
            options.OnlyRequiredInSamples();
            options.SortPropsAlphabetically();
            #endregion
        });

        //return app;
    }
}
