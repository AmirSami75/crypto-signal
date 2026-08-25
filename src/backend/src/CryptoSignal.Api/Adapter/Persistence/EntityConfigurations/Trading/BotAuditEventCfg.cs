using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// The append-only audit chain: candle → model version → signal → decision → intent → risk → order →
/// fill → position → reconciliation, one row per link.
/// </summary>
/// <remarks>
/// <para>
/// The chain-reference columns are deliberately plain nullable ids with no foreign keys. An audit event
/// must be writable even when the thing it describes failed to persist — the row recording "the venue
/// response was ambiguous" is exactly the row whose <c>ExchangeOrder</c> may not exist. A foreign key
/// here would drop the evidence at the moment it matters most.
/// </para>
/// <para>
/// <c>(CorrelationId, Sequence)</c> is unique so one tick's events have a single, gap-checkable order;
/// two writers cannot interleave into the same slot and leave the chain unreadable.
/// </para>
/// </remarks>
public sealed class BotAuditEventCfg : BaseEntityTypeConfiguration<BotAuditEvent>
{
    public override void Configure(EntityTypeBuilder<BotAuditEvent> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.CorrelationId).HasMaxLength(64).IsUnicode(false);
        builder.Property(x => x.Summary).HasMaxLength(500).IsUnicode();
        builder.Property(x => x.Symbol).HasMaxLength(30).IsUnicode(false);
        builder.Property(x => x.ModelVersion).HasMaxLength(128).IsUnicode(false);
        builder.Property(x => x.ActorUserName).HasMaxLength(256).IsUnicode();

        // jsonb, so an investigation can query into the payload rather than grepping text. Never
        // carries credentials or a signed request body — see BotAuditEvent's own remarks.
        builder.Property(x => x.DetailJson).HasColumnType("jsonb");

        builder.Property(x => x.OperatingMode).HasConversion<int>();
        builder.Property(x => x.EventType).HasConversion<int>();

        #endregion

        #region Indexes

        // One slot per position in a tick's chain.
        builder.HasIndex(x => new { x.CorrelationId, x.Sequence })
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_BotAuditEvents_CorrelationId_Sequence");

        builder.HasIndex(x => new { x.BotId, x.OccurredAt })
            .HasDatabaseName("IX_BotAuditEvents_BotId_OccurredAt");

        builder.HasIndex(x => new { x.EventType, x.OccurredAt })
            .HasDatabaseName("IX_BotAuditEvents_EventType_OccurredAt");

        #endregion
    }
}
