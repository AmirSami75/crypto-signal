using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Infra.Base.Enums;

public enum ApiResultStatusCode
{
    [Display(Name = "عملیات با موفقیت انجام شد")]
    Success = 200,

    [Display(Name = "خطایی در سرور رخ داده است")]
    ServerError = 500,

    [Display(Name = "پارامتر های ارسالی معتبر نیستند")]
    BadRequest = 400,

    [Display(Name = "موردی یافت نشد")]
    NotFound = 404,

    [Display(Name = "شما اجازه دسترسی به این منبع را ندارید")]
    Forbidden = 403,           // 403 - Authenticated but not permitted

    [Display(Name = "احراز هویت ناموفق بود")]
    Unauthorized = 401,        // 401 - Not authenticated

    [Display(Name = "درخواست با این وضعیت امکان‌پذیر نیست")]
    Conflict = 409,

    [Display(Name = "خطا در اعتبارسنجی داده‌ها")]
    ValidationError = 422,     // Optional: Unprocessable Entity

    [Display(Name = "بدون محتوا")]
    NoContent = 204,

    [Display(Name = "سرور در حال حاضر قادر به پاسخگویی نیست")]
    ServiceUnavailable = 503,
}