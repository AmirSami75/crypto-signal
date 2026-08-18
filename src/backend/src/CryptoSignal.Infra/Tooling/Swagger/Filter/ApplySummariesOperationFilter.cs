using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.OpenApi.Models;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Extensions.Type;
using Pluralize.NET;
using Swashbuckle.AspNetCore.SwaggerGen;
using System.Reflection;
using System.Xml.XPath;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

public class ApplySummariesOperationFilter : IOperationFilter
{
	public void Apply(OpenApiOperation operation, OperationFilterContext context)
	{
		var controllerActionDescriptor = context.ApiDescription.ActionDescriptor as ControllerActionDescriptor;
		if (controllerActionDescriptor == null) return;

		var controllerInfo = controllerActionDescriptor.ControllerTypeInfo.GetCustomAttribute<ControllerInfoAttribute>();
		var pluralizer = new Pluralizer();
		var actionName = controllerActionDescriptor.ActionName;
		var singularizeName = pluralizer.Singularize(controllerActionDescriptor.ControllerName);
		var pluralizeName = pluralizer.Pluralize(singularizeName);

		var parameterCount = operation.Parameters.Where(p => p.Name != "version" && p.Name != "api-version").Count();

		if ((IsActionName("Search")))
		{
			if (!operation.Summary.HasValue())
				operation.Summary = $"جستجوی {controllerInfo?.Caption}";
		}
		else if (IsActionName("Post", "Create"))
		{
			if (!operation.Summary.HasValue())
				operation.Summary = $"افزودن {controllerInfo?.Caption}";
		}
		else if (IsActionName("Read", "Get"))
		{
			if (!operation.Summary.HasValue())
				operation.Summary = $"دریافت اطلاعات {controllerInfo?.Caption}";
		}
		else if (IsActionName("Put", "Edit", "Update"))
		{
			if (!operation.Summary.HasValue())
				operation.Summary = $"ویرایش {controllerInfo?.Caption}";
		}
		else if (IsActionName("Delete", "Remove", "SoftDelete"))
		{
			if (!operation.Summary.HasValue())
				operation.Summary = $"حذف {controllerInfo?.Caption}";
		}
		else
		{
        }

		#region Local Functions
		bool IsGetAllAction()
		{
			foreach (var name in new[] { "Get", "Read", "Select", "Post" })
			{
				if ((actionName.Equals(name, StringComparison.OrdinalIgnoreCase) && parameterCount == 0) ||
					actionName.Equals($"{name}All", StringComparison.OrdinalIgnoreCase) ||
					actionName.Equals($"{name}{pluralizeName}", StringComparison.OrdinalIgnoreCase) ||
					actionName.Equals($"{name}All{singularizeName}", StringComparison.OrdinalIgnoreCase) ||
					actionName.Equals($"{name}All{pluralizeName}", StringComparison.OrdinalIgnoreCase))
				{
					return true;
				}
			}
			return false;
		}

		bool IsActionName(params string[] names)
		{
			foreach (var name in names)
			{
				if (actionName.Equals(name, StringComparison.OrdinalIgnoreCase) ||
					actionName.Equals($"{name}ById", StringComparison.OrdinalIgnoreCase) ||
					actionName.Equals($"{name}{singularizeName}", StringComparison.OrdinalIgnoreCase) ||
					actionName.Equals($"{name}{singularizeName}ById", StringComparison.OrdinalIgnoreCase))
				{
					return true;
				}
			}
			return false;
		}
		#endregion
	}
}
