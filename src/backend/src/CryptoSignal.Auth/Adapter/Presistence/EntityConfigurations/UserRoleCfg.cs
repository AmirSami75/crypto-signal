using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Auth.Adapter.Presistence.EntityConfigurations;

public sealed class UserRoleCfg : BaseEntityTypeConfiguration<UserRole>
{
    public override void Configure(EntityTypeBuilder<UserRole> builder)
    {
        #region Properties

        builder.Ignore(ur => ur.Id);
        builder.HasKey(ur => new { ur.UserId, ur.RoleId });


        base.Configure(builder);

        #endregion

        #region Relationships
        
        builder.HasOne(x => x.BaseUser)
            .WithMany(x => x.UserRoles)
            .HasForeignKey(x => x.UserId)
            .OnDelete(DeleteBehavior.Cascade);
        
        builder.HasOne(x => x.Role)
            .WithMany(x => x.UserRoles)
            .HasForeignKey(x => x.RoleId)
            .OnDelete(DeleteBehavior.Cascade);

        #endregion

        #region Indexes

        // Reverse lookup by Role
        builder.HasIndex(x => x.RoleId)
            .HasDatabaseName("IX_UserRoles_RoleId");

        // Symmetric lookup by User
        builder.HasIndex(x => x.UserId)
            .HasDatabaseName("IX_UserRoles_UserId");
        
        #endregion
    }
}