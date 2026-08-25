using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// The risk engine's verdict on one intent, kept whether it allowed or denied.
/// </summary>
/// <remarks>
/// Bound one-to-one to its intent by the unique index: an intent is evaluated exactly once, and the
/// row records the snapshot the checks ran against so a denial is as auditable as a fill. A refusal is
/// evidence, not an error to be discarded (<c>LIVE_TRADING_SAFETY.md</c>).
/// </remarks>
public sealed class RiskDecisionCfg : BaseEntityTypeConfiguration<RiskDecision>
{
    public override void Configure(EntityTypeBuilder<RiskDecision> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        // A CSV of failed RiskCheck member names; the snapshot is the JSON the checks ran against.
        builder.Property(x => x.FailedChecksCsv).HasMaxLength(1000).IsUnicode(false);
        builder.Property(x => x.Detail).HasMaxLength(2000).IsUnicode();

        // jsonb, so a post-mortem can query the limits the checks actually saw rather than parse text.
        builder.Property(x => x.SnapshotJson).HasColumnType("jsonb");

        #endregion

        #region Relationships

        builder.HasOne<OrderIntent>()
            .WithMany()
            .HasForeignKey(x => x.OrderIntentId)
            .OnDelete(DeleteBehavior.Restrict);

        #endregion

        #region Indexes

        builder.HasIndex(x => x.OrderIntentId)
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_RiskDecisions_OrderIntentId");

        #endregion
    }
}
