using Asp.Versioning;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace CryptoSignal.Api.API.Controllers.v1.Core;

/// <summary>
/// Service discovery and platform metadata. Anonymous: it returns only static descriptive values.
/// </summary>
/// <remarks>
/// Routed at the version root rather than <c>[controller]</c>, so it answers on
/// <c>/api/v1</c> and <c>/api/v1/platform</c>.
/// </remarks>
[ApiVersion("1")]
[AllowAnonymous]
[ControllerInfo("Platform", "اطلاعات سامانه")]
[Route("api/v{version:apiVersion}")]
public class PlatformController(IConfiguration configuration) : BaseController
{
    /// <summary>
    /// API index — the entry point a client can crawl to discover the available endpoints.
    /// </summary>
    [HttpGet]
    public ApiResult<ApiIndex> Index() => Ok(new ApiIndex(
        Name: "Crypto ML Trading Platform API",
        Version: "v1",
        Orchestrator: "dotnet-10",
        Links: new ApiIndexLinks(
            Platform: "/api/v1/platform",
            Login: "/api/v1/auth/login",
            Users: "/api/v1/user",
            Roles: "/api/v1/role",
            Permissions: "/api/v1/permission",
            MlCapabilities: "/api/v1/ml/capabilities",
            MlModel: "/api/v1/ml/model",
            MlPrediction: "/api/v1/ml/predictions",
            Swagger: "/swagger",
            LiveHealth: "/health/live",
            ReadyHealth: "/health/ready")));

    /// <summary>
    /// Composition of the running platform and the trading mode it is operating in.
    /// </summary>
    [HttpGet("platform")]
    public ApiResult<PlatformInfo> Platform() => Ok(new PlatformInfo(
        Backend: ".NET 10 ASP.NET Core API and orchestrator",
        MachineLearning: "Python internal ML service",
        Dashboard: "React and TypeScript",
        Database: "PostgreSQL",
        OperatingMode: configuration["OperatingMode"] ?? "PAPER",
        ExecutionPolicy: "Only the .NET orchestrator may authorize exchange orders"));
}
