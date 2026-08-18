using System.Reflection;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.AspNetCore.Mvc.Filters;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;

namespace CryptoSignal.Auth.API.Attributes.Permissions;

[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
public class CustomAuthorizeAttribute() : TypeFilterAttribute(typeof(CustomAuthorizeFilter))
{
    private class CustomAuthorizeFilter(IAuthorizationService authorizationService) : IAsyncAuthorizationFilter
    {
        public async Task OnAuthorizationAsync(AuthorizationFilterContext context)
        {
            var actionDescriptor = (ControllerActionDescriptor)context.ActionDescriptor;

            // Get Permission Attribute from action
            var permissionAttr = actionDescriptor.MethodInfo.GetCustomAttribute<PermissionAttribute>();
            if (permissionAttr == null)
                return; // No permission required

            // Get ControllerInfo for service name
            var controllerInfo = actionDescriptor.ControllerTypeInfo.GetCustomAttribute<ControllerInfoAttribute>()
                ?.FullName;

            if (string.IsNullOrWhiteSpace(controllerInfo))
            {
                context.Result = new JsonResult(new ApiResult(false, ApiResultStatusCode.Unauthorized,
                    "ControllerInfoAttribute not defined on controller"));
                return;
            }

            // Build permission name dynamically
            var permissionName = permissionAttr.Type == PermissionType.Custom
                ? $"{controllerInfo}.{permissionAttr.ActionName}"
                : $"{controllerInfo}.{permissionAttr.Type}";

            // Ask the AuthorizationService to evaluate PermissionRequirement
            var result = await authorizationService.AuthorizeAsync(
                context.HttpContext.User,
                null,
                new PermissionRequirement(permissionName)
            );

            if (!result.Succeeded)
            {
                context.Result = new JsonResult(new ApiResult(false, ApiResultStatusCode.Unauthorized,
                    "مجوز سطح دسترسی شما به این سرویس نامعتبر است"));
            }
        }
    }
}