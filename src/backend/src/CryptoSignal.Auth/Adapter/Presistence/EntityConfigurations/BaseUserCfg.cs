using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Auth.Adapter.Presistence.EntityConfigurations;

public sealed class BaseUserCfg : BaseEntityTypeConfiguration<BaseUser>
{
    public override void Configure(EntityTypeBuilder<BaseUser> builder)
    {
        #region Properties

        builder.HasKey(e => e.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        base.Configure(builder);

        builder.Property(x => x.FullName).HasMaxLength(100).IsUnicode();
        builder.Property(x => x.UserName).HasMaxLength(50).IsUnicode();
        builder.Property(x => x.PersonelCode).HasMaxLength(30).IsUnicode();
        builder.Property(x => x.Email).HasMaxLength(100).IsUnicode();
        builder.Property(x => x.Phone).HasMaxLength(30).IsUnicode();
        builder.Property(x => x.Address).HasMaxLength(200).IsUnicode();
        builder.Property(x => x.Password).HasMaxLength(200).IsUnicode();

        builder.Property(x => x.IsActive).HasDefaultValue(true);
        builder.Property(x => x.IsLocked).HasDefaultValue(false);
        builder.Property(x => x.RequirePasswordChange).HasDefaultValue(false);
        builder.Property(x => x.FailedLoginAttempts).HasDefaultValue(0);

        #endregion

        #region Relationships

        builder.HasOne(x => x.Parent)
            .WithMany(x => x.Children)
            .HasForeignKey(x => x.ParentId)
            .OnDelete(DeleteBehavior.NoAction);

        #endregion

        #region Indexes

        // Login resolves a user by UserName, so a duplicate would make authentication
        // non-deterministic. Filtered on IsDeleted so a soft-deleted account does not
        // permanently reserve its username.
        builder.HasIndex(x => x.UserName)
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_Users_UserName_Active");

        builder.HasIndex(x => x.PersonelCode)
            .HasDatabaseName("IX_Users_PersonelCode");

        #endregion
    }
}