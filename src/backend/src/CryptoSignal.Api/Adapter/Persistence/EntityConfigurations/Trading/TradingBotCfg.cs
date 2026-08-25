using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// The bot's configuration row: what to trade, how big, and every risk limit the engine enforces.
/// </summary>
/// <remarks>
/// The risk limits are stored but not defended here — a zero limit is a valid value that the risk
/// engine reads as "deny", never as "unlimited" (see <c>LIVE_TRADING_SAFETY.md</c>). What the schema
/// does defend is the trade shape: a barrier at zero distance is touched on entry, so the percentages
/// and the notional must be strictly positive, and the cadence cannot be zero or the scheduler would
/// spin.
/// </remarks>
public sealed class TradingBotCfg : BaseEntityTypeConfiguration<TradingBot>
{
    public override void Configure(EntityTypeBuilder<TradingBot> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.Name).HasMaxLength(120).IsUnicode();
        builder.Property(x => x.Description).HasMaxLength(500).IsUnicode();
        builder.Property(x => x.Symbol).HasMaxLength(30).IsUnicode(false);
        builder.Property(x => x.Interval).HasMaxLength(10).IsUnicode(false);
        builder.Property(x => x.StatusReason).HasMaxLength(500).IsUnicode();
        builder.Property(x => x.ExpectedModelVersion).HasMaxLength(128).IsUnicode(false);

        // Persisted as numeric values so renaming an enum member cannot reinterpret stored rows.
        builder.Property(x => x.Venue).HasConversion<int>();
        builder.Property(x => x.OperatingMode).HasConversion<int>();
        builder.Property(x => x.Status).HasConversion<int>();

        #endregion

        #region Indexes

        builder.HasIndex(x => x.Name)
            .IsUnique()
            .HasFilter("""
                       "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_TradingBots_Name_Active");

        // The scheduler sweeps for bots to evaluate by status; keep that lookup cheap.
        builder.HasIndex(x => x.Status)
            .HasDatabaseName("IX_TradingBots_Status");

        builder.HasIndex(x => new { x.OperatingMode, x.Symbol, x.Interval })
            .HasDatabaseName("IX_TradingBots_Mode_Symbol_Interval");

        #endregion

        #region Constraints - Data Quality

        builder.ToTable(tb =>
        {
            // A barrier at zero distance from entry is touched immediately; both percentages must
            // clear zero. Notional and cadence likewise cannot be zero for a runnable bot.
            tb.HasCheckConstraint(
                "CK_TradingBots_TakeProfitPercent_Positive",
                @"""TakeProfitPercent"" > 0");
            tb.HasCheckConstraint(
                "CK_TradingBots_StopLossPercent_Positive",
                @"""StopLossPercent"" > 0");
            tb.HasCheckConstraint(
                "CK_TradingBots_QuoteNotionalPerTrade_Positive",
                @"""QuoteNotionalPerTrade"" > 0");
            tb.HasCheckConstraint(
                "CK_TradingBots_CadenceSeconds_Positive",
                @"""CadenceSeconds"" > 0");
        });

        #endregion
    }
}
