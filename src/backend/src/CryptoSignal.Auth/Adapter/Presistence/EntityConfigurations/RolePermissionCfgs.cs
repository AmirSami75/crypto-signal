using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Auth.Adapter.Presistence.EntityConfigurations;

public sealed class RolePermissionCfgs : BaseEntityTypeConfiguration<RolePermission>
{
    public override void Configure(EntityTypeBuilder<RolePermission> builder)
    {
        #region Properties

        builder.Ignore(rp => rp.Id);
        builder.HasKey(rp => new { rp.RoleId, rp.PermissionId });
        base.Configure(builder);

        #endregion

        #region Relationships

        builder.HasOne(x => x.Role)
            .WithMany(x => x.RolePermissions)
            .HasForeignKey(x => x.RoleId)
            .OnDelete(DeleteBehavior.Cascade);

        builder.HasOne(x => x.Permission)
            .WithMany(x => x.RolePermissions)
            .HasForeignKey(x => x.PermissionId)
            .OnDelete(DeleteBehavior.Cascade);

        #endregion

        #region Indexes

        builder.HasIndex(x => x.PermissionId)
            .HasDatabaseName("IX_RolePermissions_PermissionId");

        builder.HasIndex(x => x.RoleId)
            .HasDatabaseName("IX_RolePermissions_RoleId");

        #endregion
    }
}