using System.Net.Http.Headers;
using HotChocolate.Execution.Configuration;
using Microsoft.AspNetCore.Cors.Infrastructure;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;

namespace CryptoSignal.Infra.Tooling.Graphql;

public static class GraphqlServer
{
    /// <summary>
    /// Adds a GraphQL server to the ASP.NET service container with dynamic configurations.
    /// You can customize the GraphQL server, add remote schemas for schema stitching, and configure CORS policies.
    /// </summary>
    /// <param name="services">The IServiceCollection to add services to.</param>
    /// <param name="configureGraphQl">An optional action to configure the GraphQL server.</param>
    /// <param name="remoteSchemas">An optional dictionary of remote schemas for schema stitching.</param>
    /// <param name="configureCors">An optional tuple containing a CORS policy name and configuration action.</param>
    /// <returns>The modified IServiceCollection.</returns>
    public static void InjectGraphQlServices(this IServiceCollection services,
        Action<IRequestExecutorBuilder>? configureGraphQl = null,
        Dictionary<string, string>? remoteSchemas = null,
        Tuple<string, Action<CorsPolicyBuilder>>? configureCors = null,
        bool useFiltering = false)
    {
        if (configureCors is not null)
        {
            services.AddCors(opts =>
                opts.AddPolicy(configureCors.Item1, configureCors.Item2));
        }

        var svc = services
            .AddGraphQLServer();

        if (useFiltering)
        {
            svc = services
                .AddGraphQLServer().AddFiltering();
        }


        configureGraphQl?.Invoke(svc);

        if (remoteSchemas == null) return;

        foreach (var remoteSchema in remoteSchemas)
        {
            svc.Services.AddHttpClient(remoteSchema.Key, (sp, client) =>
            {
                client.BaseAddress = new Uri(remoteSchema.Value);

                var httpContextAccessor = sp.GetRequiredService<IHttpContextAccessor>();
                var httpContext = httpContextAccessor.HttpContext;

                var token = httpContext?.Request.Headers.Authorization.ToString();

                if (!string.IsNullOrEmpty(token))
                {
                    client.DefaultRequestHeaders.Authorization =
                        new AuthenticationHeaderValue("Bearer", token.Replace("Bearer ", ""));
                }
            });
            
            svc.AddRemoteSchema(remoteSchema.Key, ignoreRootTypes: true);
        }
    }
}