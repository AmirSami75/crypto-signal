using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Base.Entity;
using System.ComponentModel.DataAnnotations.Schema;

namespace CryptoSignal.Auth.Domain.Models
{
    public sealed class RolePermission : BaseEntity
    {
        #region Properties
        public Guid RoleId { get; set; }
        public Guid PermissionId { get; set; }
        #endregion

        #region Navigation Property
        [ForeignKey(nameof(RoleId))]
        public Role? Role { get; set; }

        [ForeignKey(nameof(PermissionId))]
        public Permission? Permission { get; set; }
        #endregion
    }

}
