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

            // Keeps the token across reloads. Without this the Authorize dialog is emptied by every
            // refresh — including the one the UI performs when you switch between doc versions — so a
            // token pasted a minute ago is silently gone and the next call comes back 401. That reads as
            // "swagger auth is broken" long before anyone suspects the page reload.
            //
            // The cost is explicit: swagger-ui persists to **localStorage** (key "authorized"), not
            // sessionStorage, so the raw JWT stays at rest for this origin across tabs and restarts
            // until someone hits Logout in the dialog. That matches what the dashboard already does with
            // its own token, and this is a docs page for an API whose tokens are short-lived — but it is
            // a bearer credential written to disk, so note that UseSwaggerAndUI is currently called
            // unconditionally in Program.cs, for every environment.
            options.EnablePersistAuthorization();
            //  options.ShowExtensions();

            //// Network
            // EnableValidator() is deliberately *not* called. It points the "spec valid" badge at
            // https://online.swagger.io/validator, which works by having the browser hand the whole
            // document to a third party — and this one describes every endpoint and DTO of a private
            // trading API. Omitting the call is what disables it: swagger-ui's own bootstrap sets
            // `validatorUrl = null` when the config object does not carry the key. There is no
            // DisableValidator() on SwaggerUIOptions in Swashbuckle 10.x to say so more loudly.
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
