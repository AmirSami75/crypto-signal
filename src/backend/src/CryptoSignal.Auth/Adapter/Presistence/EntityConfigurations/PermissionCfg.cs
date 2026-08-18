using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Auth.Adapter.Presistence.EntityConfigurations;

public sealed class PermissionCfg : BaseEntityTypeConfiguration<Permission>
{
    public override void Configure(EntityTypeBuilder<Permission> builder)
    {
        # region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.Name).HasMaxLength(150).IsUnicode(true);
        builder.Property(x => x.Title).HasMaxLength(300).IsUnicode(true);

        #endregion

        #region Relationships
        // (relations are configured on join tables)
        #endregion

        #region Indexes

        builder.HasIndex(x => x.Name)
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_Permissions_Name_Active");

        builder.HasIndex(x => x.Title)
            .HasDatabaseName("IX_Permissions_Title");


        #endregion
        #region Constraints - Data Quality

        builder.ToTable(tb =>
        {
            // PostgreSQL: double-quoted identifiers are case-sensitive and match the mapped column.
            tb.HasCheckConstraint(
                "CK_Permissions_Name_NotEmpty",
                @"TRIM(""Name"") <> ''");
        });

        #endregion
    }
}