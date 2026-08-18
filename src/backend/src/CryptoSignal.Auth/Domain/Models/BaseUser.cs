using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Auth.Domain.Models;

public abstract class BaseUser : BaseEntity
{
    #region polymorphic-boundry

    public virtual string? BranchName => null;

    public virtual string? BranchCode => null;

    #endregion

    #region Properties

    public Guid? ParentId { get; set; }

    public string FullName { get; set; }

    public string UserName { get; set; }

    public string? PersonelCode { get; set; }

    public string? Email { get; set; }

    public string? Phone { get; set; }

    public string? Address { get; set; }

    public string Password { get; set; }

    public int FailedLoginAttempts { get; set; } = 0;

    public bool IsActive { get; set; } = true;

    public bool IsLocked { get; set; } = false;

    public bool RequirePasswordChange { get; set; } = true;

    public Guid SecurityStamp { get; set; } = Guid.CreateVersion7();

    public DateTime? LastPasswordChangedAt { get; set; }

    #endregion

    #region Navigation Properties

    public ICollection<UserRole> UserRoles { get; set; }
    public ICollection<LoginHistory> LoginHistories { get; set; }

    [ForeignKey(nameof(ParentId))] public virtual BaseUser? Parent { get; set; }
    public ICollection<BaseUser>? Children { get; set; }

    #endregion
}