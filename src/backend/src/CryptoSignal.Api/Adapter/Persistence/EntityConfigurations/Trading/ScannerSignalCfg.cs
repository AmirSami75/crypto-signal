using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// Configuration for <see cref="ScannerSignal"/> — the market scanner's proposal rows.
/// Each signal is claimed atomically by scanner-mode bots to prevent duplicate orders.
/// </summary>
public sealed class ScannerSignalCfg : BaseEntityTypeConfiguration<ScannerSignal>
{
    public override void Configure(EntityTypeBuilder<ScannerSignal> builder)
    {
        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.ScanId)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.Symbol).HasMaxLength(30).IsUnicode(false);
        builder.Property(x => x.Interval).HasMaxLength(10).IsUnicode(false);
        builder.Property(x => x.StrategyKey).HasMaxLength(60).IsUnicode(false);
        builder.Property(x => x.Direction).HasConversion<int>();
        builder.Property(x => x.Reason).HasMaxLength(500).IsUnicode();

        // The scanner writes signals; bots claim them. Index the unclaimed ones.
        builder.HasIndex(x => x.TakenByBotId)
            .HasDatabaseName("IX_ScannerSignals_TakenByBotId");

        // Fast lookup by symbol + interval + unclaimed.
        builder.HasIndex(x => new { x.Symbol, x.Interval, x.StrategyKey, x.TakenByBotId })
            .HasDatabaseName("IX_ScannerSignals_Symbol_Interval_Strategy_Claimed");

        builder.ToTable(tb => tb.HasCheckConstraint(
            "CK_ScannerSignals_Confidence_InRange",
            "\"Confidence\" >= 0.0 AND \"Confidence\" <= 1.0"));
    }
}
