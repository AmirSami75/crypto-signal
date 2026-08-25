using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>One execution against an order: price, quantity, and the fee the venue charged.</summary>
/// <remarks>
/// The unique index on <c>(Venue, VenueTradeId)</c> makes fill ingestion idempotent — polling the same
/// trade twice, or reconciling after a dropped response, inserts the fill once. Without it a retried
/// poll would double the realised quantity and silently corrupt the position's P&amp;L.
/// </remarks>
public sealed class OrderFillCfg : BaseEntityTypeConfiguration<OrderFill>
{
    public override void Configure(EntityTypeBuilder<OrderFill> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.VenueTradeId).HasMaxLength(64).IsUnicode(false);
        builder.Property(x => x.FeeAsset).HasMaxLength(20).IsUnicode(false);

        builder.Property(x => x.OperatingMode).HasConversion<int>();
        builder.Property(x => x.Venue).HasConversion<int>();

        #endregion

        #region Relationships

        builder.HasOne<ExchangeOrder>()
            .WithMany()
            .HasForeignKey(x => x.ExchangeOrderId)
            .OnDelete(DeleteBehavior.Restrict);

        #endregion

        #region Indexes

        // One row per venue trade; a re-polled fill must not be counted twice.
        builder.HasIndex(x => new { x.Venue, x.VenueTradeId })
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_OrderFills_Venue_VenueTradeId");

        builder.HasIndex(x => x.ExchangeOrderId)
            .HasDatabaseName("IX_OrderFills_ExchangeOrderId");

        #endregion
    }
}
