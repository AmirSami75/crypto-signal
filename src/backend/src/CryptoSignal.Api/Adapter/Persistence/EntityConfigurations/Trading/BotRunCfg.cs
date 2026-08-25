using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>One scheduler lease over one bot, with its tick counters and last failure.</summary>
/// <remarks>
/// The partial unique index is the schema half of the single-runner guarantee: at most one row per bot
/// may have <c>EndedAt</c> null. The advisory lock in the scheduler stops two replicas racing within a
/// tick; this index stops a leaked lease from ever becoming two concurrent runs of the same bot, which
/// would double every order it places.
/// </remarks>
public sealed class BotRunCfg : BaseEntityTypeConfiguration<BotRun>
{
    public override void Configure(EntityTypeBuilder<BotRun> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.LeaseOwner).HasMaxLength(128).IsUnicode(false);
        builder.Property(x => x.LastError).HasMaxLength(2000).IsUnicode();
        builder.Property(x => x.OperatingMode).HasConversion<int>();

        #endregion

        #region Relationships

        builder.HasOne<TradingBot>()
            .WithMany()
            .HasForeignKey(x => x.BotId)
            .OnDelete(DeleteBehavior.Restrict);

        #endregion

        #region Indexes

        // At most one open run per bot. Rows are soft-deleted, so the filter excludes those too.
        builder.HasIndex(x => x.BotId)
            .IsUnique()
            .HasFilter("""
                       "EndedAt" IS NULL AND "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_BotRuns_BotId_Open");

        builder.HasIndex(x => new { x.BotId, x.StartedAt })
            .HasDatabaseName("IX_BotRuns_BotId_StartedAt");

        #endregion
    }
}
