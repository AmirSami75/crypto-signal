using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Auth.Adapter.Presistence.EntityConfigurations;

public class RoleCfg : BaseEntityTypeConfiguration<Role>
{
    public override void Configure(EntityTypeBuilder<Role> builder)
    {

        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();
        builder.Property(x => x.Name).HasMaxLength(100).IsUnicode(true);
        builder.Property(x => x.Title).HasMaxLength(200).IsUnicode(true);

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
            .HasDatabaseName("UX_Roles_Name_Active");

        builder.HasIndex(x => x.Title)
            .HasDatabaseName("IX_Roles_Title");

        #endregion
        
        #region Constraints - Data Quality

        builder.ToTable(tb =>
        {
            // Name not empty/whitespace. PostgreSQL TRIM('  ') returns '' (not NULL, unlike Oracle),
            // so the emptiness has to be compared explicitly.
            tb.HasCheckConstraint(
                "CK_Roles_Name_NotEmpty",
                @"TRIM(""Name"") <> ''");
        });

        #endregion
    }
}