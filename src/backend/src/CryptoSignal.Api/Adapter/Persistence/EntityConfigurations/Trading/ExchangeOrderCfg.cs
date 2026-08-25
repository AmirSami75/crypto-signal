using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// The venue's side of an order: its id there, its status, and hashes of the traffic — never the
/// bodies, which would carry signed credentials.
/// </summary>
/// <remarks>
/// <c>VenueOrderId</c> is nullable because an order can be in-flight or ambiguous: the request left but
/// no acknowledgement came back. That state is reconciled by <c>ClientOrderId</c>, which is why the
/// client id is indexed here too. Only request/response <em>hashes</em> are stored; a Binance payload
/// contains an HMAC signature and must never be persisted verbatim.
/// </remarks>
public sealed class ExchangeOrderCfg : BaseEntityTypeConfiguration<ExchangeOrder>
{
    public override void Configure(EntityTypeBuilder<ExchangeOrder> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.VenueOrderId).HasMaxLength(64).IsUnicode(false);
        builder.Property(x => x.ClientOrderId).HasMaxLength(64).IsUnicode(false);
        builder.Property(x => x.RequestHash).HasMaxLength(64).IsUnicode(false);
        builder.Property(x => x.ResponseHash).HasMaxLength(64).IsUnicode(false);

        builder.Property(x => x.OperatingMode).HasConversion<int>();
        builder.Property(x => x.Venue).HasConversion<int>();
        builder.Property(x => x.Status).HasConversion<int>();

        #endregion

        #region Relationships

        builder.HasOne<OrderIntent>()
            .WithMany()
            .HasForeignKey(x => x.OrderIntentId)
            .OnDelete(DeleteBehavior.Restrict);

        #endregion

        #region Indexes

        // Reconciliation looks the order up by the client id it was submitted under.
        builder.HasIndex(x => x.ClientOrderId)
            .HasDatabaseName("IX_ExchangeOrders_ClientOrderId");

        // A venue order id, once known, identifies exactly one order per venue.
        builder.HasIndex(x => new { x.Venue, x.VenueOrderId })
            .IsUnique()
            .HasFilter("""
                       "VenueOrderId" IS NOT NULL AND "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_ExchangeOrders_Venue_VenueOrderId");

        #endregion
    }
}
