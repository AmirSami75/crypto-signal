using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Infra.Base.Entity;
using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Auth.Domain.Models;


public sealed class Role : BaseEntity
{
    #region Properties
    [Display(Name = "نام")]
    public string Name { get; set; }

    [Display(Name = "عنوان")]
    public string Title { get; set; }

    [Display(Name = "نوع نقش")]
    public RoleType Type { get; set; }

    #endregion

    #region Navigation Properties
    public ICollection<UserRole>? UserRoles { get; set; }
    public ICollection<RolePermission>? RolePermissions { get; set; }
    #endregion
}
