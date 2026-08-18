using Microsoft.AspNetCore.Authorization;

namespace CryptoSignal.Auth.API.Attributes.Permissions;

public class PermissionRequirement(string permissionName) : IAuthorizationRequirement
{
    public string PermissionName { get; } = permissionName;
}