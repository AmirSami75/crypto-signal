// using Microsoft.AspNetCore.Mvc.Filters;
// using Sanjino.Common.Base.API;
// using Sanjino.Common.Base.Enums;
//
// namespace Sanjino.Common.Attributes;
//
// public class ValidateModelAttribute : ActionFilterAttribute
// {
//     override public void OnActionExecuting(ActionExecutingContext context)
//     {
//         if (!context.ModelState.IsValid)
//         {
//             var errors = context.ModelState
//                 .Where(e => e.Value.Errors.Any())
//                 .ToDictionary(
//                     kv => kv.Key,
//                     kv => kv.Value.Errors.Select(e => e.ErrorMessage).ToArray()
//                 );
//
//             context.Result = new ApiResult
//                 (false, ApiResultStatusCode.BadRequest, "خطای اعتبار سنجی");
//         }
//     }
// }

