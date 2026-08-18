using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Auth.Domain.Enums
{
    public enum RoleType
    {
        [Display(Description = "مدیر سیستم")] SuperAdmin,
        [Display(Description = "کاربر عادی")] User,
        [Display(Description = "کاربر")] Custom
    }
}