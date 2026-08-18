using System.Reflection;
using Asp.Versioning;
using FluentValidation;
using FluentValidation.AspNetCore;
using Mapster;
using MapsterMapper;
using Microsoft.AspNetCore.Mvc.Authorization;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Newtonsoft.Json;
using Newtonsoft.Json.Converters;
using CryptoSignal.Infra.Base.DB.Interceptors;
using CryptoSignal.Infra.Settings;
using CryptoSignal.Infra.Settings.Logging;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;
using Scrutor;

namespace CryptoSignal.Infra.Tooling.Registrations;

public static class CoreSvcInjections
{
    public static void InjectApiSettings(this IServiceCollection services, IConfiguration cfg)
    {
        // Jwt Settings
        services.Configure<JwtSettings>(cfg.GetSection("API_Settings:Jwt"));
        services.AddSingleton(sp => sp.GetRequiredService<IOptions<JwtSettings>>().Value);

        // Logging Settings
        services.Configure<LoggingSettings>(cfg.GetSection("API_Settings:Logging"));
        services.AddSingleton(sp => sp.GetRequiredService<IOptions<LoggingSettings>>().Value);

        // Db Settings
        services.Configure<DbSettings>(cfg.GetSection("API_Settings:Db"));
        services.AddSingleton(sp => sp.GetRequiredService<IOptions<DbSettings>>().Value);
    }

    public static void InjectDbContext<T>(this IServiceCollection services,
        ServiceLifetime serviceLifetime = ServiceLifetime.Scoped)
        where T : DbContext
    {
        services.AddDbContext<T>((sp, opts) =>
        {
            var dbSettings = sp.GetRequiredService<DbSettings>();

            if (!string.Equals(dbSettings.Type, DbSettings.PostgreSql, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    $"Unsupported database provider '{dbSettings.Type}'. Crypto Signal supports only '{DbSettings.PostgreSql}'.");
            }

            if (string.IsNullOrWhiteSpace(dbSettings.PostgreSqlCnnStr))
            {
                throw new InvalidOperationException(
                    "API_Settings:Db:PostgreSqlCnnStr is required.");
            }

            opts.UseNpgsql(dbSettings.PostgreSqlCnnStr, npgsqlOpts =>
            {
                npgsqlOpts.CommandTimeout(dbSettings.CommandTimeoutSeconds);

                // Off unless explicitly asked for, and deliberately so. EnableRetryOnFailure installs
                // NpgsqlRetryingExecutionStrategy, which refuses to run inside a transaction the caller
                // began itself ("does not support user-initiated transactions"). This codebase uses
                // BeginTransactionAsync in the user seeder and across the user and role controllers, so
                // a non-zero MaxRetryCount turns every one of those writes into a runtime failure unless
                // the call site also wraps the transaction in Database.CreateExecutionStrategy().
                if (dbSettings.MaxRetryCount > 0)
                {
                    npgsqlOpts.EnableRetryOnFailure(
                        dbSettings.MaxRetryCount,
                        TimeSpan.FromSeconds(dbSettings.MaxRetryDelaySeconds),
                        errorCodesToAdd: null);
                }
            });

            // save changes interceptor
            // var saveChangesInterceptor = sp.GetRequiredService<SaveChangesInterceptor>();
            // opts.AddInterceptors(saveChangesInterceptor);

            // ef cmd tracer
            var loggingSettings = sp.GetRequiredService<LoggingSettings>();
            if (loggingSettings.EfCommandTracer?.Enabled == true)
            {
                var tracer = sp.GetRequiredService<EfCommandTracer>();
                opts.AddInterceptors(tracer);
            }

            // Audit UserCtx interceptor
            var userCtxInterceptor = sp.GetRequiredService<AuditCurrentUserInterceptor>();
            opts.AddInterceptors(userCtxInterceptor);
        }, serviceLifetime);
    }

    public static void AddMinimalMvc(this IServiceCollection services)
    {
        services.AddControllers(options =>
        {
            options.Filters.Add(new AuthorizeFilter()); //Apply AuthorizeFilter as global filter to all actions

            //Like [ValidateAntiforgeryToken] attribute but dose not validatie for GET and HEAD http method
            //You can ingore validate by using [IgnoreAntiforgeryToken] attribute
            //Use this filter when use cookie 
            //options.Filters.Add(new AutoValidateAntiforgeryTokenAttribute());
            //options.UseYeKeModelBinder();
        }).AddNewtonsoftJson(option =>
        {
            option.SerializerSettings.Converters.Add(new StringEnumConverter());
            option.SerializerSettings.ReferenceLoopHandling = ReferenceLoopHandling.Ignore;
            //option.SerializerSettings.Formatting = Newtonsoft.Json.Formatting.Indented;
            //option.SerializerSettings.NullValueHandling = Newtonsoft.Json.NullValueHandling.Ignore;
        });
        services.AddSwaggerGenNewtonsoftSupport();
    }

    public static void AddCustomApiVersioning(this IServiceCollection services)
    {
        services.AddApiVersioning(options =>
        {
            //url segment => {version}
            options.AssumeDefaultVersionWhenUnspecified = true; //default => false;
            options.DefaultApiVersion = new ApiVersion(1, 0); //v1.0 == v1
            options.ReportApiVersions = true;

            //ApiVersion.TryParse("1.0", out var version10);
            //ApiVersion.TryParse("1", out var version1);
            //var a = version10 == version1;

            //options.ApiVersionReader = new QueryStringApiVersionReader("api-version");
            // api/posts?api-version=1

            //options.ApiVersionReader = new UrlSegmentApiVersionReader();
            // api/v1/posts

            //options.ApiVersionReader = new HeaderApiVersionReader(new[] { "Api-Version" });
            // header => Api-Version : 1

            //options.ApiVersionReader = new MediaTypeApiVersionReader()

            //options.ApiVersionReader = ApiVersionReader.Combine(new QueryStringApiVersionReader("api-version"), new UrlSegmentApiVersionReader())
            // combine of [querystring] & [urlsegment]
        });
    }

    public static IServiceCollection AddFluentValidationModule(
        this IServiceCollection service,
        params Assembly[] assemblies
    )
    {
        // Enable FluentValidation auto-validation globally (for model validation)
        service.AddFluentValidationAutoValidation();

        service.Scan(scan => scan
            .FromAssemblies(assemblies)
            .AddClasses(c => c.AssignableTo(typeof(IValidator<>)))
            .AsImplementedInterfaces()
            .WithTransientLifetime());

        return service;
    }

    public static IServiceCollection AddMapsterModule(this IServiceCollection services, params Assembly[] assemblies)
    {
        var config = MapsterBootstrapper.Bootstrap(assemblies);
        services.AddSingleton(config);
        services.AddScoped<IMapper, ServiceMapper>();
        services.AddScoped<IMapperAdapter, MapperAdapter>();

        return services;
    }
}