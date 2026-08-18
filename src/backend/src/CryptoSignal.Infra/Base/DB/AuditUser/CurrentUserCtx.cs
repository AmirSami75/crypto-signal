using System.Security.Claims;
using Microsoft.AspNetCore.Http;
using CryptoSignal.Infra.Base.Markers;
using CryptoSignal.Infra.Extensions.Auth;

namespace CryptoSignal.Infra.Base.DB.AuditUser;

public class CurrentUserCtx(IHttpContextAccessor accessor) : ICurrentUserCtx, IScopedInfraMarker
{
    private ClaimsIdentity? ClaimsIdentity => accessor.HttpContext?.User.Identities.First();

    public Guid? UserId => ClaimsIdentity?.GetUserId<Guid>();
    public string? UserFullName => ClaimsIdentity?.FindFirstValue(ClaimTypes.GivenName);
}