using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// The immutable record of one evaluation: what the model saw, what it said, and what the orchestrator
/// decided to do about it.
/// </summary>
/// <remarks>
/// The unique index on <c>(BotId, CandleOpenTime)</c> is the idempotency anchor for the whole chain —
/// the policy's "one intent per strategy decision" begins here as "one decision per bot per candle". A
/// tick that re-evaluates the same closed candle (a retry, a replica overlap, a restarted lease) is
/// rejected at insert, so it can never spawn a second order for a bar already acted on.
/// </remarks>
public sealed class StrategyDecisionCfg : BaseEntityTypeConfiguration<StrategyDecision>
{
    public override void Configure(EntityTypeBuilder<StrategyDecision> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.Symbol).HasMaxLength(30).IsUnicode(false);
        builder.Property(x => x.Interval).HasMaxLength(10).IsUnicode(false);
        builder.Property(x => x.CandleWindowDigest).HasMaxLength(64).IsUnicode(false);
        builder.Property(x => x.ReasonCode).HasMaxLength(64).IsUnicode(false);
        builder.Property(x => x.ModelId).HasMaxLength(128).IsUnicode(false);
        builder.Property(x => x.ModelVersion).HasMaxLength(128).IsUnicode(false);
        builder.Property(x => x.Warning).HasMaxLength(1000).IsUnicode();
        builder.Property(x => x.EngineRequestId).HasMaxLength(64).IsUnicode(false);

        builder.Property(x => x.OperatingMode).HasConversion<int>();
        builder.Property(x => x.Action).HasConversion<int>();
        builder.Property(x => x.Direction).HasConversion<int>();

        #endregion

        #region Relationships

        builder.HasOne<TradingBot>()
            .WithMany()
            .HasForeignKey(x => x.BotId)
            .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne<BotRun>()
            .WithMany()
            .HasForeignKey(x => x.BotRunId)
            .OnDelete(DeleteBehavior.SetNull);

        #endregion

        #region Indexes

        // One decision per bot per closed candle. The whole idempotency chain hangs off this.
        builder.HasIndex(x => new { x.BotId, x.CandleOpenTime })
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_StrategyDecisions_BotId_CandleOpenTime");

        #endregion
    }
}
