using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Auth.Adapter.Presistence.EntityConfigurations;

public sealed class LoginHistoryCfg : BaseEntityTypeConfiguration<LoginHistory>
{
    public override void Configure(EntityTypeBuilder<LoginHistory> builder)
    {
        #region Properties

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        base.Configure(builder);

        builder.Property(x => x.Ip).HasMaxLength(50).IsUnicode(true);
        builder.Property(x => x.UserAgent).HasMaxLength(300).IsUnicode(true);

        #endregion

        #region Relationships

        builder.HasOne(x => x.BaseUser)
            .WithMany(lh => lh.LoginHistories)
            .HasForeignKey(x => x.UserId)
            .OnDelete(DeleteBehavior.Cascade);

        # endregion
        
        #region Indexes
        
        // By user & recent first
        builder.HasIndex(x => new { x.UserId, x.CreatedAt })
            .HasDatabaseName("IX_LoginHistory_User_CreatedAt");
        
        // Global recent logins
        builder.HasIndex(x => x.CreatedAt)
            .HasDatabaseName("IX_LoginHistory_CreatedAt");
        
        // Status-focused (e.g., failed logins)
        builder.HasIndex(x => new { x.Status, x.CreatedAt })
            .HasDatabaseName("IX_LoginHistory_Status_CreatedAt");
        
        # endregion
        
        #region Constraints - Data Quality
        
        
        builder.ToTable(tb =>
        {
            // Status should be within allowed range if it's an enum stored as smallint/int.
            tb.HasCheckConstraint(
                "CK_LoginHistory_Status_Range",
                """
                "Status" >= 0 AND "Status" <= 5
                """);
        });
        #endregion
    }
}