using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// The order the orchestrator wants placed, derived from exactly one strategy decision.
/// </summary>
/// <remarks>
/// Two unique indexes carry the idempotency guarantee to the venue. One decision yields at most one
/// intent (<c>StrategyDecisionId</c> unique), and the <c>ClientOrderId</c> — computed deterministically
/// from the decision id — is unique per row, so a retried submission reuses the same id the venue
/// already knows and is deduplicated there rather than filled twice.
/// </remarks>
public sealed class OrderIntentCfg : BaseEntityTypeConfiguration<OrderIntent>
{
    public override void Configure(EntityTypeBuilder<OrderIntent> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.ClientOrderId).HasMaxLength(64).IsUnicode(false);
        builder.Property(x => x.Symbol).HasMaxLength(30).IsUnicode(false);
        builder.Property(x => x.StatusReason).HasMaxLength(500).IsUnicode();

        builder.Property(x => x.OperatingMode).HasConversion<int>();
        builder.Property(x => x.Leverage).HasDefaultValue(1);
        builder.Property(x => x.Direction).HasConversion<int>();
        builder.Property(x => x.Side).HasConversion<int>();
        builder.Property(x => x.Type).HasConversion<int>();
        builder.Property(x => x.TimeInForce).HasConversion<int?>();
        builder.Property(x => x.Status).HasConversion<int>();

        #endregion

        #region Relationships

        builder.HasOne<StrategyDecision>()
            .WithMany()
            .HasForeignKey(x => x.StrategyDecisionId)
            .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne<TradingBot>()
            .WithMany()
            .HasForeignKey(x => x.BotId)
            .OnDelete(DeleteBehavior.Restrict);

        #endregion

        #region Indexes

        // One intent per decision.
        builder.HasIndex(x => x.StrategyDecisionId)
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_OrderIntents_StrategyDecisionId");

        // The client order id is the venue-facing idempotency key; it must be globally unique.
        builder.HasIndex(x => x.ClientOrderId)
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_OrderIntents_ClientOrderId");

        builder.HasIndex(x => new { x.BotId, x.Status })
            .HasDatabaseName("IX_OrderIntents_BotId_Status");

        #endregion

        #region Constraints - Data Quality

        builder.ToTable(tb =>
        {
            tb.HasCheckConstraint(
                "CK_OrderIntents_Quantity_Positive",
                @"""Quantity"" > 0");
        });

        #endregion
    }
}
