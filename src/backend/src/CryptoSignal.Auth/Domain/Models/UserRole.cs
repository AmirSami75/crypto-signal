using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Auth.Domain.Models;


public sealed class UserRole : BaseEntity
{
    #region Properties
    public Guid UserId { get; set; }
    public Guid RoleId { get; set; }


    #endregion

    #region Navigation Properties

    [ForeignKey(nameof(UserId))]
    public BaseUser BaseUser { get; set; }

    [ForeignKey(nameof(RoleId))]
    public Role Role { get; set; }

    #endregion
}