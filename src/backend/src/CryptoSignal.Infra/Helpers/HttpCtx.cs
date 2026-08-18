using System.Security.Claims;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Primitives;

namespace CryptoSignal.Infra.Helpers;

public static class HttpCtx
{
    private static readonly IHttpContextAccessor _http = new HttpContextAccessor();

    public static (Guid? userId, string? ip) GetRequesterContext()
    {
        var ctx = _http.HttpContext;

        string? ip = null;
        if (ctx?.Request?.Headers is not null &&
            ctx.Request.Headers.TryGetValue("X-Forwarded-For", out StringValues xff) &&
            !StringValues.IsNullOrEmpty(xff))
        {
            ip = xff.ToString().Split(',')[0].Trim();
        }

        ip ??= ctx?.Connection?.RemoteIpAddress?.ToString();

        Guid? userId = null;
        var idStr =
            ctx?.User?.FindFirstValue(ClaimTypes.NameIdentifier) ??
            ctx?.User?.FindFirstValue("sub") ??
            ctx?.User?.FindFirstValue("userId");

        if (Guid.TryParse(idStr, out var gid))
            userId = gid;

        return (userId, ip);
    }
}