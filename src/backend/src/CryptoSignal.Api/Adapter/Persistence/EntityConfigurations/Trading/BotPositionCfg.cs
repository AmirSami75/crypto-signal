using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// A position as the orchestrator holds it — the engine keeps none. Realised and unrealised P&amp;L are
/// separate columns because they are different facts: one is booked, the other is a mark at a stated time.
/// </summary>
/// <remarks>
/// A bot holds at most one open position per operating mode at a time, enforced by the partial unique
/// index on <c>(BotId, OperatingMode)</c> where the status is open. Paper and sandbox positions on the
/// same bot are distinct rows and never net against each other — mode isolation is a schema property,
/// not a convention the caller must remember.
/// </remarks>
public sealed class BotPositionCfg : BaseEntityTypeConfiguration<BotPosition>
{
    public override void Configure(EntityTypeBuilder<BotPosition> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.Symbol).HasMaxLength(30).IsUnicode(false);

        builder.Property(x => x.OperatingMode).HasConversion<int>();
        builder.Property(x => x.Venue).HasConversion<int>();
        builder.Property(x => x.Direction).HasConversion<int>();
        builder.Property(x => x.Status).HasConversion<int>();
        builder.Property(x => x.CloseReason).HasConversion<int?>();

        #endregion

        #region Relationships

        builder.HasOne<TradingBot>()
            .WithMany()
            .HasForeignKey(x => x.BotId)
            .OnDelete(DeleteBehavior.Restrict);

        #endregion

        #region Indexes

        // At most one open position per bot per mode.
        builder.HasIndex(x => new { x.BotId, x.OperatingMode })
            .IsUnique()
            .HasFilter("""
                       "Status" = 1 AND "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_BotPositions_BotId_OperatingMode_Open");

        builder.HasIndex(x => new { x.BotId, x.OpenedAt })
            .HasDatabaseName("IX_BotPositions_BotId_OpenedAt");

        #endregion

        #region Constraints - Data Quality

        builder.ToTable(tb =>
        {
            tb.HasCheckConstraint(
                "CK_BotPositions_Quantity_Positive",
                @"""Quantity"" > 0");
        });

        #endregion
    }
}
