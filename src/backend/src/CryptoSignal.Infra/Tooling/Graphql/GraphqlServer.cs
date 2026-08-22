using HotChocolate.Execution.Configuration;
using Microsoft.AspNetCore.Cors.Infrastructure;
using Microsoft.Extensions.DependencyInjection;

namespace CryptoSignal.Infra.Tooling.Graphql;

public static class GraphqlServer
{
    /// <summary>
    /// Adds a GraphQL server to the ASP.NET service container with dynamic configurations.
    /// You can customize the GraphQL server and configure CORS policies.
    /// </summary>
    /// <param name="services">The IServiceCollection to add services to.</param>
    /// <param name="configureGraphQl">An optional action to configure the GraphQL server.</param>
    /// <param name="configureCors">An optional tuple containing a CORS policy name and configuration action.</param>
    /// <param name="useFiltering">Adds HotChocolate's filtering conventions to the schema.</param>
    /// <remarks>
    /// Remote-schema stitching used to be configured here. It was dropped along with the
    /// HotChocolate.Stitching package reference: stitching was removed from HotChocolate in v14 in
    /// favour of Fusion, so the last release — 13.9.16 — pulled a second, parallel HotChocolate 13.x
    /// assembly graph into a v16 build and its <c>AddRemoteSchema</c> extension could no longer bind
    /// to the v16 <c>IRequestExecutorBuilder</c>. Nothing in this deployment serves GraphQL, so there
    /// is no gateway to stitch; a future one would use Fusion rather than stitching anyway.
    /// </remarks>
    public static void InjectGraphQlServices(this IServiceCollection services,
        Action<IRequestExecutorBuilder>? configureGraphQl = null,
        Tuple<string, Action<CorsPolicyBuilder>>? configureCors = null,
        bool useFiltering = false)
    {
        if (configureCors is not null)
        {
            services.AddCors(opts =>
                opts.AddPolicy(configureCors.Item1, configureCors.Item2));
        }

        var svc = services.AddGraphQLServer();

        // Applied to the builder already created rather than calling AddGraphQLServer a second time,
        // which returned a fresh builder and silently discarded any configuration applied to the first.
        if (useFiltering)
            svc.AddFiltering();

        configureGraphQl?.Invoke(svc);
    }
}
