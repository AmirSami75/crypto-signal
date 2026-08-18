using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Base.Entity;
using CryptoSignal.Infra.Base.Enums;
using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Auth.Domain.Models;

public sealed class Permission : BaseEntity
{
    #region Properties
    [Display(Name = "نوع دسترسی")]
    public PermissionType Type { get; set; }

    [Display(Name = "نام دسترسی")]
    public string Name { get; set; }

    [Display(Name = "عنوان دسترسی")]
    public string Title { get; set; }
    #endregion

    #region Navigation Properties
    public ICollection<RolePermission>? RolePermissions { get; set; }
    #endregion
}
