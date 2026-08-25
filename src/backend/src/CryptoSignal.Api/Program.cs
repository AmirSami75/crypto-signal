using Asp.Versioning;
using System.Net;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Application.Trading.Execution;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Risk;
using CryptoSignal.Api.Adapter.Persistence.Contexts;
using CryptoSignal.Api.Adapter.Persistence.Contexts.Dapper;
using CryptoSignal.Api.Application.DTOs.Auth;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Application.Security;
using CryptoSignal.Api.Clients;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Api.Domain;
using CryptoSignal.Api.Domain.Constants;
using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Auth.Application.Services.Contracts;
using CryptoSignal.Auth.Application.Services.Implementations;
using CryptoSignal.Auth.Domain;
using CryptoSignal.Auth.Tooling.Registrations;
using CryptoSignal.Contracts.Ml.V1;
using CryptoSignal.Infra.Base;
using CryptoSignal.Infra.Base.API;
using CryptoSignal.Infra.Base.API.SearchFilter;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Base.Markers;
using CryptoSignal.Infra.Extensions.Contracts;
using CryptoSignal.Infra.Middlewares;
using CryptoSignal.Infra.RulesEngine.DI;
using CryptoSignal.Infra.Tooling.Logging;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Registrations;
using CryptoSignal.Infra.Tooling.Swagger;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.AspNetCore.Mvc.ApplicationModels;
using Microsoft.Extensions.Options;
using Serilog;
using System.Globalization;
using System.Threading.RateLimiting;

// Aliased instead of importing Microsoft.Extensions.Diagnostics.HealthChecks wholesale: that
// namespace declares its own HealthReport, which would collide with this API's probe contract.
using HealthCheckService = Microsoft.Extensions.Diagnostics.HealthChecks.HealthCheckService;
using HealthStatus = Microsoft.Extensions.Diagnostics.HealthChecks.HealthStatus;

#region Base Configs

var builder = WebApplication.CreateBuilder(args);
var services = builder.Services;
var config = builder.Configuration;
var env = builder.Environment;

List<string> apiVersions = ["v1"];

// The Auth and Infra XML files are included as well so the summaries on the inherited
// CrudController/BaseAuthController actions reach Swagger, not just the ones declared here.
List<string> apiXmlFiles = ["CryptoSignal.Api.xml", "CryptoSignal.Auth.xml", "CryptoSignal.Infra.xml"];

config
    .SetBasePath(env.ContentRootPath)
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .AddJsonFile($"appsettings.{env.EnvironmentName}.json", optional: true, reloadOnChange: true)
    .AddEnvironmentVariables()
    .AddCommandLine(args);

services.Configure<FormOptions>(o =>
{
    o.MultipartBodyLengthLimit = long.MaxValue;
    o.ValueLengthLimit = int.MaxValue;
    o.MultipartHeadersLengthLimit = int.MaxValue;
});

#endregion

#region Route Format

// Turns UserController/AccountActivation into /api/v1/user/account-activation.
services.AddControllers(options =>
{
    options.Conventions.Add(new RouteTokenTransformerConvention(new SlugifyParameterTransformer()));
});

#endregion

#region Kestrel Configurations

builder.WebHost.UseKestrel((ctx, opts) => { opts.Configure(ctx.Configuration.GetSection("Kestrel")); });

#endregion

#region Logging

Log.Logger = SerilogConfigComposer
    .Compose(configuration: config,
    [
        typeof(IApiMarker).Assembly,
        typeof(IAuthMarker).Assembly,
        typeof(IInfraMarker).Assembly
    ])
    .CreateLogger();

builder.Host.UseSerilog();

services.AddSingleton(typeof(ILoggerAdapter<>), typeof(LoggerAdapter<>));

#endregion

#region Options & Clients

services
    .AddOptions<BootstrapSettings>()
    .Bind(config.GetSection(BootstrapSettings.SectionName))
    .ValidateDataAnnotations();

services
    .AddOptions<MlServiceOptions>()
    .Bind(config.GetSection(MlServiceOptions.SectionName))
    .Validate(
        value => Uri.TryCreate(value.Address, UriKind.Absolute, out _),
        "MlService:Address must be an absolute URI")
    .Validate(value => value.DeadlineSeconds is >= 1 and <= 300,
        "MlService:DeadlineSeconds must be between 1 and 300")
    .Validate(value => value.MaxReceiveMessageMb is >= 1 and <= 256,
        "MlService:MaxReceiveMessageMb must be between 1 and 256")
    .ValidateOnStart();

services
    .AddGrpcClient<MlEngineService.MlEngineServiceClient>((sp, client) =>
    {
        var options = sp.GetRequiredService<IOptions<MlServiceOptions>>().Value;
        client.Address = new Uri(options.Address, UriKind.Absolute);
    })
    .ConfigureChannel((sp, channel) =>
    {
        var options = sp.GetRequiredService<IOptions<MlServiceOptions>>().Value;
        channel.MaxReceiveMessageSize = options.MaxReceiveMessageMb * 1_048_576;
    });

services.AddSingleton<IMlServiceClient, MlServiceClient>();

// ── Trading: exchange & market-data options ──────────────────────────────────────
// Credentials are bound from the environment only (Exchange__BinanceTestnet__ApiKey /
// __ApiSecret). An empty key is not a validation failure: a venue with no credentials is one this
// deployment cannot trade, and that must be a normal, quiet state rather than a startup crash.
services
    .AddOptions<ExchangeOptions>()
    .Bind(config.GetSection(ExchangeOptions.SectionName))
    .Validate(value => value.RecvWindowMs is >= 1000 and <= 60_000,
        "Exchange:RecvWindowMs must be between 1000 and 60000")
    .Validate(value => value.RequestTimeoutSeconds is >= 1 and <= 120,
        "Exchange:RequestTimeoutSeconds must be between 1 and 120")
    .ValidateOnStart();

services
    .AddOptions<MarketDataOptions>()
    .Bind(config.GetSection(MarketDataOptions.SectionName))
    .ValidateOnStart();

services
    .AddOptions<PaperBrokerOptions>()
    .Bind(config.GetSection(PaperBrokerOptions.SectionName))
    .Validate(value => value.SlippageBps is >= 0 and <= 1000,
        "Trading:Paper:SlippageBps must be between 0 and 1000")
    .Validate(value => value.FeeBps is >= 0 and <= 1000,
        "Trading:Paper:FeeBps must be between 0 and 1000")
    .Validate(value => value.QuoteBalance >= 0,
        "Trading:Paper:QuoteBalance cannot be negative")
    .ValidateOnStart();

// Exchange connections: keys stored AES-GCM sealed, resolved per user at tick time. The master key is
// validated on start so a missing or malformed value surfaces as a startup failure — never as a
// runtime surprise after an operator believes their key was saved.
services
    .AddOptions<KeyProtectionOptions>()
    .Bind(config.GetSection(KeyProtectionOptions.SectionName))
    .Validate(value => !string.IsNullOrWhiteSpace(value.KeyEncryptionKey),
        "Sercurity:KeyEncryptionKey is required — exchange API keys cannot be stored without it")
    .Validate(value => Convert.TryFromBase64String(value.KeyEncryptionKey, new byte[32], out _),
        "Sercurity:KeyEncryptionKey must be a base64 32-byte value")
    .ValidateOnStart();

// The bot loop, and the only place in this application that submits an order. It is a hosted
// service rather than anything reachable over HTTP because an HTTP request can be replayed by a
// refresh or a retrying proxy, and a replayed submit is a duplicate trade
// (docs/LIVE_TRADING_SAFETY.md). Registered unconditionally: the service reads
// Trading:SchedulerEnabled itself and idles when it is false, which keeps "why is nothing running"
// answerable from a log line instead of from the absence of one.
services.AddHostedService<BotSchedulerService>();

// ── Trading: scheduler & platform risk ceilings ──────────────────────────────────
// Two sections, deliberately: "Trading" decides when a bot is looked at, "Trading:Risk" decides
// whether an order may be placed. Keeping them apart means a cadence change cannot widen a limit.
//
// Neither is validated into existence. Every risk default already denies — empty allowlists, zero
// maxima, live execution off — so a missing or misnamed section produces a deployment that trades
// nothing rather than one that refuses to start. Validation here only rejects values that are
// incoherent rather than merely restrictive: a negative limit, or a poll interval of zero.
services
    .AddOptions<TradingOptions>()
    .Bind(config.GetSection(TradingOptions.SectionName))
    .Validate(value => value.PollSeconds is >= 1 and <= 3600,
        "Trading:PollSeconds must be between 1 and 3600")
    .Validate(value => value.MaxBotsPerCycle is >= 1 and <= 1000,
        "Trading:MaxBotsPerCycle must be between 1 and 1000")
    .Validate(value => value.CandleWindowSize is >= 50 and <= 1500,
        "Trading:CandleWindowSize must be between 50 and 1500")
    .Validate(value => value.TickTimeoutSeconds is >= 5 and <= 600,
        "Trading:TickTimeoutSeconds must be between 5 and 600")
    .Validate(value => value.LeaseStaleSeconds >= value.PollSeconds * 2,
        "Trading:LeaseStaleSeconds must be at least twice Trading:PollSeconds, or a healthy worker's lease expires under it")
    .ValidateOnStart();

services
    .AddOptions<TradingRiskOptions>()
    .Bind(config.GetSection(TradingRiskOptions.SectionName))
    .Validate(value => value.MaxOrderNotional >= 0
                       && value.MaxPositionNotional >= 0
                       && value.MaxDailyLoss >= 0
                       && value.MaxOrdersPerDay >= 0
                       && value.MaxConcurrentPositions >= 0
                       && value.MaxCandleAgeIntervals >= 0
                       && value.MaxConsecutiveFailures >= 0,
        "No Trading:Risk limit may be negative — zero already denies, and a negative value would only obscure that")
    .Validate(value => value.MaxLeverage >= 1, "Trading:Risk:MaxLeverage must be at least 1")

    // Spot cannot borrow to sell what it does not hold. A config claiming both is not restrictive,
    // it is contradictory, and the contradiction must surface at startup rather than as a broker
    // rejection on the first short.
    .Validate(value => !(value.SpotOnly && value.AllowShorting),
        "Trading:Risk cannot set both SpotOnly and AllowShorting — a spot account cannot short")
    .Validate(value => !(value.AllowLiveExecution && !value.EnabledOperatingModes.Contains(
                             nameof(OperatingMode.Live), StringComparer.OrdinalIgnoreCase)),
        "Trading:Risk:AllowLiveExecution is true but LIVE is not in EnabledOperatingModes")
    .ValidateOnStart();

// One named client per venue, shared by that venue's kline source, rule provider and broker, so a
// sandbox broker can never borrow the mainnet channel. The handler lifetime is short because the
// venue rotates DNS; the timeout is what turns an unanswered write into an explicit ambiguous
// outcome rather than a hung tick.
AddVenueClient(MarketVenue.BinanceTestnet);
AddVenueClient(MarketVenue.BinanceMainnet);
AddVenueClient(MarketVenue.Bitunix);

void AddVenueClient(MarketVenue venue)
{
    var exchange = config.GetSection(ExchangeOptions.SectionName).Get<ExchangeOptions>() ?? new ExchangeOptions();

    var httpBuilder = services
        .AddHttpClient(TradingHttpClients.ForVenue(venue), client =>
        {
            client.BaseAddress = new Uri(exchange.RestBaseUrl(venue), UriKind.Absolute);
            client.Timeout = TimeSpan.FromSeconds(exchange.RequestTimeoutSeconds);
            client.DefaultRequestHeaders.Add("Accept", "application/json");
        })
        .SetHandlerLifetime(TimeSpan.FromMinutes(5));

    // Mainnet is unreachable from inside the containers without one. Configured per venue and never
    // inherited from the environment: an order silently leaving through an unexpected proxy is a
    // worse failure than one that does not leave at all.
    var proxyUrl = exchange.For(venue).ProxyUrl;
    httpBuilder.ConfigurePrimaryHttpMessageHandler(() =>
        string.IsNullOrWhiteSpace(proxyUrl)
            ? new HttpClientHandler { UseProxy = false }
            : new HttpClientHandler
            {
                UseProxy = true,
                Proxy = new WebProxy(proxyUrl),
            });
}

services.AddHttpContextAccessor();

#endregion

#region Service Injections

services.AddScoped(typeof(IAuthService<>), typeof(AuthService<>));
services.AddScoped<IAuthorizationHandler, PermissionHandler>();

// Repo Injections
services.Scan(scan => scan
    .FromAssemblies(
        typeof(IInfraMarker).Assembly // Infra  --> (Repo<>, IRepo<>)
        , typeof(IAuthMarker).Assembly // Auth   --> (BaseRoleRepo + ...)
        , typeof(IApiMarker).Assembly // Api    --> (UserRepo + ...)
    )
    .AddClasses(c => c.AssignableTo(typeof(IRepo<>)))
    .AsImplementedInterfaces()
    .WithScopedLifetime()
);

// Search Query Specification Injections
services.Scan(scan => scan
    .FromAssemblies(
        typeof(IInfraMarker).Assembly // Infra  --> (ExpressionSearchFilterQuery<,>)
        , typeof(IAuthMarker).Assembly // Auth   --> (RoleQuerySpecification + ...)
        , typeof(IApiMarker).Assembly // Api    --> (UserQuerySpecification)
    )
    .AddClasses(c => c.AssignableTo(typeof(ExpressionSearchFilterQuery<,>)))
    .AsSelf()
    .WithScopedLifetime()
);

// Seeders Injections — ordering is honoured by IEntitySeedData.Order, not registration order.
services.Scan(scan => scan
    .FromAssemblies(
        typeof(IInfraMarker).Assembly
        , typeof(IAuthMarker).Assembly // Auth   --> (PermissionSeeder + RoleSeeder)
        , typeof(IApiMarker).Assembly // Api    --> (UserSeeder)
    )
    .AddClasses(c => c.AssignableTo<IEntitySeedData>())
    .As<IEntitySeedData>()
    .WithScopedLifetime()
);

// String Normalizer Injections --> cleans strings before they reach the database
services.Scan(scan => scan
    .FromAssemblies(typeof(IInfraMarker).Assembly)
    .AddClasses(c => c.AssignableTo<IStringNormalizer>())
    .As<IStringNormalizer>()
    .WithSingletonLifetime()
);

// Infra utility injections
services.Scan(scan => scan
    .FromAssemblyOf<IInfraMarker>()
    .AddClasses(c => c.AssignableTo<IScopedInfraMarker>())
    .AsSelf().AsImplementedInterfaces().WithScopedLifetime()
    .AddClasses(c => c.AssignableTo<ITransientInfraMarker>())
    .AsSelf().AsImplementedInterfaces().WithTransientLifetime()
    .AddClasses(c => c.AssignableTo<ISingletonInfraMarker>())
    .AsSelf().AsImplementedInterfaces().WithSingletonLifetime()
);

// Application service injections
services.Scan(scan => scan
    .FromAssemblyOf<IApiMarker>()
    .AddClasses(c => c.AssignableTo<ISingletonSvcMarker>())
    .AsSelf().AsImplementedInterfaces().WithSingletonLifetime()
    .AddClasses(c => c.AssignableTo<IScopedSvcMarker>())
    .AsSelf().AsImplementedInterfaces().WithScopedLifetime()
);

// Credential sealing and resolution for stored exchange connections.
services.AddSingleton<SecretProtector>();
services.AddScoped<ICredentialProvider, CredentialProvider>();

// Rule engine — also registers IRuleEngine<> and ICrudRuleExecutor<,,>
services.AddRuleEngines(typeof(IApiMarker).Assembly);

// DB Context Injection
services.InjectDbContext<CryptoSignalDbContext>();

// API Settings Injection (API_Settings:Db / :Jwt / :Logging)
services.InjectApiSettings(config);

// Custom Api Features Injection
services.AddMinimalMvc();

// Jwt Service Injection
services.InjectJwtAuth<User>();

// Api Versioning Injection
services.AddCustomApiVersioning();

// Swagger Documentation Injection
services.AddSwagger(new SwaggerConfigurationBuilder()
    .SetXMLFilesName(apiXmlFiles)
    .SetVersions(apiVersions)
    .SetApiName("CryptoSignal.Api")
    .Build());

// Mapper Injection
services.AddMapsterModule(typeof(SessionUserDto).Assembly, typeof(RoleInputDto).Assembly);

// Fluent-Validation Injection
services.AddFluentValidationModule([typeof(IApiMarker).Assembly, typeof(IAuthMarker).Assembly]);

#endregion

#region Rate Limiting

// The only anonymous write endpoint is POST /api/v1/auth/register, and it is the only thing
// limited here. Login needs no counterpart: it already locks an account after
// AuthGlobalVariables.NumberOfWrongPasswordsAllowed failures, which bounds guessing against a
// known username. Nothing comparable bounds how many *new* accounts a caller can create, so a
// fixed window per client IP is the floor.
services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;

    // A rejection is produced by this middleware, upstream of both MVC and
    // UnifiedExceptionHandlerMiddleware, so neither shapes the body — without this a client would
    // get a bare 429 with no payload. Written by hand to keep the same IsSuccess/StatusCode/Message
    // envelope every other error uses. WriteAsJsonAsync applies the app's web JSON defaults, so
    // these names go out camelCase, matching MVC's success envelope.
    options.OnRejected = async (context, ct) =>
    {
        if (context.Lease.TryGetMetadata(MetadataName.RetryAfter, out var retryAfter))
            context.HttpContext.Response.Headers.RetryAfter =
                ((int)retryAfter.TotalSeconds).ToString(CultureInfo.InvariantCulture);

        await context.HttpContext.Response.WriteAsJsonAsync(
            new
            {
                IsSuccess = false,

                // The literal HTTP status, not an ApiResultStatusCode: that enum has no 429
                // member, and a body that disagreed with the status line would be worse than a
                // number the client already understands.
                StatusCode = StatusCodes.Status429TooManyRequests,
                Message = "تعداد درخواست‌های شما بیش از حد مجاز است. لطفا کمی بعد دوباره تلاش کنید",
            },
            ct);
    };

    options.AddPolicy(RateLimitPolicies.Registration, httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            // Partition by remote IP. Behind the compose stack's nginx this is the proxy address
            // unless forwarded headers are honoured, which they are not today — so treat this as a
            // coarse guard against a single unsophisticated source, not as per-user accounting.
            partitionKey: httpContext.Connection.RemoteIpAddress?.ToString() ?? "unknown",
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = RateLimitPolicies.RegistrationPermitLimit,
                Window = TimeSpan.FromMinutes(RateLimitPolicies.RegistrationWindowMinutes),

                // No queue: a caller over the limit should be told so immediately rather than have
                // the request held open.
                QueueLimit = 0,
                QueueProcessingOrder = QueueProcessingOrder.OldestFirst,
            }));

    // Bot start / pause / stop. Bounded because each transition writes an audit row and ends or opens
    // a lease, so a hammered endpoint pollutes the chain an incident review has to read. Loose enough
    // that an operator managing a fleet by hand never meets it.
    options.AddPolicy(RateLimitPolicies.BotControl, httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: httpContext.Connection.RemoteIpAddress?.ToString() ?? "unknown",
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = RateLimitPolicies.BotControlPermitLimit,
                Window = TimeSpan.FromMinutes(RateLimitPolicies.BotControlWindowMinutes),
                QueueLimit = 0,
                QueueProcessingOrder = QueueProcessingOrder.OldestFirst,
            }));

    // The kill switch is deliberately the loosest policy here. Engaging one is the safe action, and an
    // operator stopping trading in an emergency must never be told to wait — a limit that could delay
    // an emergency stop would be a safety defect dressed as a load control.
    options.AddPolicy(RateLimitPolicies.KillSwitchControl, httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: httpContext.Connection.RemoteIpAddress?.ToString() ?? "unknown",
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = RateLimitPolicies.KillSwitchPermitLimit,
                Window = TimeSpan.FromMinutes(RateLimitPolicies.KillSwitchWindowMinutes),
                QueueLimit = 0,
                QueueProcessingOrder = QueueProcessingOrder.OldestFirst,
            }));
});

#endregion

#region CORS

var allowedOrigins = config
    .GetSection("Cors:AllowedOrigins")
    .GetChildren()
    .Select(item => item.Value)
    .Where(value => !string.IsNullOrWhiteSpace(value))
    .Cast<string>()
    .ToArray();

services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        // No configured origins means no cross-origin access, rather than a wildcard. Credentials
        // are allowed because the JWT can travel in an Authorization cookie, and a wildcard origin
        // is invalid in that combination anyway.
        if (allowedOrigins.Length > 0)
            policy.WithOrigins(allowedOrigins).AllowAnyHeader().AllowAnyMethod().AllowCredentials();
    });
});

#endregion

#region Health Checks

services.AddHealthChecks()
    .AddCheck<PostgreSqlHealthCheck>("postgresql");

#endregion

#region Pipeline Configurations

try
{
    Log.Information("Booting up CryptoSignal API ...");

    var app = builder.Build();

    if (env.IsDevelopment())
        app.UseDeveloperExceptionPage();
    else if (env.IsProduction())
    {
        app.UseHsts();
        app.UseHttpsRedirection();
    }

    app.UseSwaggerAndUI(apiVersions);

    app.UseCors();

    app.UseMiddleware<UnifiedExceptionHandlerMiddleware>();

    // Creates the schema if absent, runs IDbObjectInitializers, then the ordered seeders
    // (permissions -> roles -> bootstrap superadmin).
    await app.UseDatabaseInitialization<CryptoSignalDbContext>();

    app.UseRouting();

    // After UseRouting so the endpoint — and therefore its [EnableRateLimiting] policy — is known,
    // and before authentication so an anonymous flood is rejected without touching the database.
    app.UseRateLimiter();

    app.UseAuthentication();
    app.UseAuthorization();

    app.MapControllers();

    #region Probes

    // Kept outside the ApiResult envelope and the version prefix so container orchestrators and
    // load balancers can consume them without knowing this API's conventions.
    app.MapGet("/health/live", () => Results.Ok(
        new HealthReport("dotnet-orchestrator", "healthy", DateTimeOffset.UtcNow)));

    app.MapGet("/health/ready", async (
        HealthCheckService healthChecks,
        IMlServiceClient mlService,
        CancellationToken ct) =>
    {
        var dbReport = await healthChecks.CheckHealthAsync(ct);
        var dbHealthy = dbReport.Status == HealthStatus.Healthy;

        var mlHealth = await mlService.GetHealthAsync(ct);
        var mlHealthy = mlHealth.Status.Equals("healthy", StringComparison.OrdinalIgnoreCase);

        var isReady = dbHealthy && mlHealthy;

        return Results.Json(
            new HealthReport(
                "dotnet-orchestrator",
                isReady ? "healthy" : "degraded",
                DateTimeOffset.UtcNow,
                [
                    new DependencyHealth(
                        "postgresql",
                        dbHealthy ? "healthy" : "unhealthy",
                        dbReport.Entries.TryGetValue("postgresql", out var entry) ? entry.Description : null),
                    mlHealth
                ]),
            statusCode: isReady ? StatusCodes.Status200OK : StatusCodes.Status503ServiceUnavailable);
    });

    #endregion

    app.Run();
}
catch (Exception ex)
{
    Log.Fatal(ex, "CryptoSignal API terminated unexpectedly!");
}
finally
{
    Log.CloseAndFlush();
}

#endregion
