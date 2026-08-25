using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// A recorded candle, so any decision the engine made can be replayed against the exact window it saw.
/// </summary>
/// <remarks>
/// Keyed by venue rather than by operating mode, unlike every other table in this module: a candle is
/// a fact about a market, not a portfolio, and the same testnet candle legitimately backs both a paper
/// and a sandbox bot. The venue is part of the key because two venues' prices for one symbol are two
/// different facts and must never collapse into one row.
/// </remarks>
public sealed class MarketCandleCfg : BaseEntityTypeConfiguration<MarketCandle>
{
    public override void Configure(EntityTypeBuilder<MarketCandle> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.Symbol).HasMaxLength(30).IsUnicode(false);
        builder.Property(x => x.Interval).HasMaxLength(10).IsUnicode(false);
        builder.Property(x => x.Venue).HasConversion<int>();

        #endregion

        #region Indexes

        builder.HasIndex(x => new { x.Venue, x.Symbol, x.Interval, x.OpenTime })
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_MarketCandles_Venue_Symbol_Interval_OpenTime");

        #endregion

        #region Constraints - Data Quality

        builder.ToTable(tb =>
        {
            // A candle whose high is below its low is a parse error, not a market event.
            tb.HasCheckConstraint(
                "CK_MarketCandles_HighNotBelowLow",
                @"""High"" >= ""Low""");
            tb.HasCheckConstraint(
                "CK_MarketCandles_CloseTimeAfterOpenTime",
                @"""CloseTime"" > ""OpenTime""");
        });

        #endregion
    }
}
