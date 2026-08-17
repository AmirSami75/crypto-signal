using CryptoMlSignal.Api.Clients;
using CryptoMlSignal.Api.Contracts;
using CryptoMlSignal.Api.Options;
using CryptoMlSignal.Contracts.Ml.V1;
using Microsoft.Extensions.Options;

var builder = WebApplication.CreateBuilder(args);

builder.Services
    .AddOptions<MlServiceOptions>()
    .Bind(builder.Configuration.GetSection(MlServiceOptions.SectionName))
    .Validate(
        value => Uri.TryCreate(value.Address, UriKind.Absolute, out _),
        "MlService:Address must be an absolute URI")
    .Validate(value => value.DeadlineSeconds is >= 1 and <= 300)
    .Validate(value => value.MaxReceiveMessageMb is >= 1 and <= 256)
    .ValidateOnStart();
builder.Services
    .AddGrpcClient<MlEngineService.MlEngineServiceClient>((services, client) =>
    {
        var options = services.GetRequiredService<IOptions<MlServiceOptions>>().Value;
        client.Address = new Uri(options.Address, UriKind.Absolute);
    })
    .ConfigureChannel((services, channel) =>
    {
        var options = services.GetRequiredService<IOptions<MlServiceOptions>>().Value;
        channel.MaxReceiveMessageSize = options.MaxReceiveMessageMb * 1_048_576;
    });
builder.Services.AddSingleton<IMlServiceClient, MlServiceClient>();

var allowedOrigins = builder.Configuration
    .GetSection("Cors:AllowedOrigins")
    .GetChildren()
    .Select(item => item.Value)
    .Where(value => !string.IsNullOrWhiteSpace(value))
    .Cast<string>()
    .ToArray();

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        if (allowedOrigins.Length > 0)
        {
            policy.WithOrigins(allowedOrigins).AllowAnyHeader().AllowAnyMethod();
        }
    });
});

var app = builder.Build();

app.UseCors();

app.MapGet("/health/live", () => Results.Ok(new
{
    service = "dotnet-orchestrator",
    status = "healthy",
    timestamp = DateTimeOffset.UtcNow,
}));

app.MapGet("/health/ready", async (
    IMlServiceClient mlService,
    CancellationToken cancellationToken) =>
{
    var mlHealth = await mlService.GetHealthAsync(cancellationToken);
    var isReady = mlHealth.Status.Equals("healthy", StringComparison.OrdinalIgnoreCase);
    return Results.Json(
        new
        {
            service = "dotnet-orchestrator",
            status = isReady ? "healthy" : "degraded",
            dependencies = new[] { mlHealth },
            timestamp = DateTimeOffset.UtcNow,
        },
        statusCode: isReady ? StatusCodes.Status200OK : StatusCodes.Status503ServiceUnavailable);
});

var api = app.MapGroup("/api/v1");

api.MapGet("/", () => Results.Ok(new
{
    name = "Crypto ML Trading Platform API",
    version = "v1",
    orchestrator = "dotnet-10",
    links = new
    {
        platform = "/api/v1/platform",
        mlCapabilities = "/api/v1/ml/capabilities",
        mlModel = "/api/v1/ml/model",
        mlPrediction = "/api/v1/ml/predictions",
        liveHealth = "/health/live",
        readyHealth = "/health/ready",
    },
}));

api.MapGet("/platform", (IConfiguration configuration) => Results.Ok(new
{
    backend = ".NET 10 ASP.NET Core API and orchestrator",
    machineLearning = "Python internal ML service",
    dashboard = "React and TypeScript",
    database = "PostgreSQL",
    operatingMode = configuration["OperatingMode"] ?? "PAPER",
    executionPolicy = "Only the .NET orchestrator may authorize exchange orders",
}));

api.MapGet("/ml/capabilities", async (
    IMlServiceClient mlService,
    CancellationToken cancellationToken) =>
{
    var capabilities = await mlService.GetCapabilitiesAsync(cancellationToken);
    return capabilities is null
        ? Results.Problem(
            title: "Python ML service unavailable",
            statusCode: StatusCodes.Status503ServiceUnavailable)
        : Results.Ok(capabilities);
});

api.MapGet("/ml/model", async (
    IMlServiceClient mlService,
    CancellationToken cancellationToken) =>
{
    var model = await mlService.GetModelInfoAsync(cancellationToken);
    return model is null
        ? Results.Problem(
            title: "Python ML model unavailable",
            statusCode: StatusCodes.Status503ServiceUnavailable)
        : Results.Ok(model);
});

api.MapPost("/ml/predictions", async (
    MlPredictionRequest request,
    IMlServiceClient mlService,
    CancellationToken cancellationToken) =>
{
    if (request.Candles is null || request.Candles.Count == 0)
    {
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            [nameof(request.Candles)] = ["At least one completed candle is required."],
        });
    }

    try
    {
        var prediction = await mlService.PredictSignalAsync(request, cancellationToken);
        return Results.Ok(prediction);
    }
    catch (MlServiceException exception)
    {
        var statusCode = exception.ErrorCode == "InvalidArgument"
            ? StatusCodes.Status400BadRequest
            : StatusCodes.Status503ServiceUnavailable;
        return Results.Problem(
            title: "ML prediction failed",
            detail: exception.Message,
            statusCode: statusCode);
    }
});

app.Run();
