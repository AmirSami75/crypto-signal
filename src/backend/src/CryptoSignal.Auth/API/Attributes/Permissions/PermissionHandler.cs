using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.EntityFrameworkCore;
using Newtonsoft.Json;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Enums;

namespace CryptoSignal.Auth.API.Attributes.Permissions;

public class PermissionHandler(
    IPermissionRepo permissionRepo,
    IRoleRepo roleRepo,
    IRolePermissionRepo rolePermissionRepo)
    : AuthorizationHandler<PermissionRequirement>
{
    protected override async Task HandleRequirementAsync(AuthorizationHandlerContext context,
        PermissionRequirement requirement)
    {
        if (!context.User.Identity?.IsAuthenticated ?? false)
            return;

        var rolesClaim = context.User.Claims.FirstOrDefault(c => c.Type == ClaimTypes.Role)?.Value;
        if (string.IsNullOrEmpty(rolesClaim))
            return;

        var roleIds = JsonConvert.DeserializeObject<List<Guid>>(rolesClaim);
        if (roleIds == null || roleIds.Count == 0)
            return;

        // Check permission existence
        var permissionEntity = await permissionRepo.TableNoTracking
            .FirstOrDefaultAsync(p => p.Name == requirement.PermissionName);

        if (permissionEntity is null)
            return;

        // Validate against roles
        foreach (var roleId in roleIds)
        {
            var role = await roleRepo.TableNoTracking.FirstOrDefaultAsync(r => r.Id == roleId);

            if (role?.Type == RoleType.SuperAdmin)
            {
                context.Succeed(requirement);
                return;
            }

            var hasPermission = await rolePermissionRepo.TableNoTracking
                .AnyAsync(rp => rp.PermissionId == permissionEntity.Id && rp.RoleId == roleId);

            if (!hasPermission) continue;
            
            context.Succeed(requirement);
            return;
        }
    }
}