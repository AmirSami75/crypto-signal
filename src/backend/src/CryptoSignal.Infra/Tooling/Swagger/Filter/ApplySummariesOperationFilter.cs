using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.OpenApi;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Extensions.Type;
using Pluralize.NET;
using Swashbuckle.AspNetCore.SwaggerGen;
using System.Reflection;

namespace CryptoSignal.Infra.Tooling.Swagger.Filter;

/// <summary>
/// Fills in a summary for conventional CRUD actions that have no XML documentation of their own,
/// using the caption from the controller's <see cref="ControllerInfoAttribute"/>. An action that
/// already carries a summary is left untouched.
/// </summary>
public class ApplySummariesOperationFilter : IOperationFilter
{
	public void Apply(OpenApiOperation operation, OperationFilterContext context)
	{
		if (context.ApiDescription.ActionDescriptor is not ControllerActionDescriptor controllerActionDescriptor)
			return;

		var controllerInfo = controllerActionDescriptor.ControllerTypeInfo.GetCustomAttribute<ControllerInfoAttribute>();

		// Nothing to interpolate into the summary templates without a caption, and the inherited
		// CrudController actions are the ones that rely on this filter — so leave them to their XML
		// documentation rather than emitting a summary with an empty subject.
		if (controllerInfo is null) return;

		// Hoisted out of every branch below: an action that documents itself via XML comments keeps
		// its own summary, and Summary is nullable in Microsoft.OpenApi 2.x so it cannot be probed
		// through the non-nullable HasValue extension.
		if (!string.IsNullOrWhiteSpace(operation.Summary)) return;

		var pluralizer = new Pluralizer();
		var actionName = controllerActionDescriptor.ActionName;
		var singularizeName = pluralizer.Singularize(controllerActionDescriptor.ControllerName);

		if (IsActionName("Search"))
		{
			operation.Summary = $"جستجوی {controllerInfo.Caption}";
		}
		else if (IsActionName("Post", "Create"))
		{
			operation.Summary = $"افزودن {controllerInfo.Caption}";
		}
		else if (IsActionName("Read", "Get"))
		{
			operation.Summary = $"دریافت اطلاعات {controllerInfo.Caption}";
		}
		else if (IsActionName("Put", "Edit", "Update"))
		{
			operation.Summary = $"ویرایش {controllerInfo.Caption}";
		}
		else if (IsActionName("Delete", "Remove", "SoftDelete"))
		{
			operation.Summary = $"حذف {controllerInfo.Caption}";
		}

		#region Local Functions

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
