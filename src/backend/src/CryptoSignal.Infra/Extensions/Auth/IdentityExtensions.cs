using System.Globalization;
using System.Security.Claims;
using System.Security.Principal;
using CryptoSignal.Infra.Extensions.Type;

namespace CryptoSignal.Infra.Extensions.Auth;

public static class IdentityExtensions
{
    public static string FindFirstValue(this ClaimsIdentity identity, string claimType)
    {
        return identity?.FindFirst(claimType)?.Value;
    }

    public static string FindFirstValue(this IIdentity identity, string claimType)
    {
        var claimsIdentity = identity as ClaimsIdentity;
        return claimsIdentity?.FindFirstValue(claimType);
    }

    public static string GetUserId(this IIdentity identity)
    {
        return identity?.FindFirstValue(ClaimTypes.NameIdentifier);
    }

    public static T GetUserId<T>(this IIdentity identity)
    {
        var userId = identity?.GetUserId();

        if (!userId.HasValue())
            return default;

        if (typeof(T) == typeof(Guid))
            return (T)(object)Guid.Parse(userId);

        return (T)Convert.ChangeType(userId, typeof(T), CultureInfo.InvariantCulture);
    }

    public static List<long> GetUserRoleIds<T>(this IIdentity identity) where T : IConvertible
    {
        var RoleIds = identity?.FindFirstValue(ClaimTypes.Role);


        return RoleIds.Split(',')
            .Select(str => long.Parse(str.Trim('[', ']')))
            .ToList();
    }


    public static string GetUserName(this IIdentity identity)
    {
        return identity?.FindFirstValue(ClaimTypes.Name);
    }
}