using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// A halt switch at some scope — global, a mode, a venue, a bot, or a symbol. Engaging one stops the
/// next tick from placing anything within its scope.
/// </summary>
/// <remarks>
/// The partial unique index allows at most one engaged switch per scope target, so "is trading halted
/// here" is a single-row question with no ambiguity to resolve under load. A disengaged switch is kept
/// as history, not deleted — who halted trading and why is part of the audit chain.
/// </remarks>
public sealed class KillSwitchCfg : BaseEntityTypeConfiguration<KillSwitch>
{
    public override void Configure(EntityTypeBuilder<KillSwitch> builder)
    {
        #region Properties

        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        builder.Property(x => x.Reason).HasMaxLength(500).IsUnicode();
        builder.Property(x => x.TriggerDetail).HasMaxLength(2000).IsUnicode();
        builder.Property(x => x.ScopeSymbol).HasMaxLength(30).IsUnicode(false);
        builder.Property(x => x.EngagedByUserName).HasMaxLength(256).IsUnicode();
        builder.Property(x => x.DisengagedByUserName).HasMaxLength(256).IsUnicode();

        builder.Property(x => x.Scope).HasConversion<int>();
        builder.Property(x => x.ScopeOperatingMode).HasConversion<int?>();
        builder.Property(x => x.ScopeVenue).HasConversion<int?>();

        #endregion

        #region Indexes

        // At most one engaged switch per scope target. The scope discriminator plus its (mutually
        // exclusive) target columns identify the target; COALESCE folds the nullable targets so two
        // engaged global switches, or two for the same bot, cannot coexist.
        builder.HasIndex(x => new
            {
                x.Scope,
                x.ScopeOperatingMode,
                x.ScopeVenue,
                x.ScopeBotId,
                x.ScopeSymbol,
            })
            .IsUnique()
            .HasFilter("""
                       "IsEngaged" = true AND "IsDeleted" = false
                       """)
            .HasDatabaseName("UX_KillSwitches_Scope_Engaged");

        #endregion

        #region Constraints - Data Quality

        builder.ToTable(tb =>
        {
            // The scope discriminator and its target column must agree: a bot-scoped switch names a
            // bot and nothing else, a global switch names no target at all. This keeps the "is trading
            // halted here" lookup honest — a mislabelled row could halt the wrong scope, or nothing.
            tb.HasCheckConstraint(
                "CK_KillSwitches_ScopeTargetMatches",
                """
                (
                    ("Scope" = 1 AND "ScopeOperatingMode" IS NULL AND "ScopeVenue" IS NULL AND "ScopeBotId" IS NULL AND "ScopeSymbol" IS NULL)
                 OR ("Scope" = 2 AND "ScopeOperatingMode" IS NOT NULL AND "ScopeVenue" IS NULL AND "ScopeBotId" IS NULL AND "ScopeSymbol" IS NULL)
                 OR ("Scope" = 3 AND "ScopeVenue" IS NOT NULL AND "ScopeOperatingMode" IS NULL AND "ScopeBotId" IS NULL AND "ScopeSymbol" IS NULL)
                 OR ("Scope" = 4 AND "ScopeBotId" IS NOT NULL AND "ScopeOperatingMode" IS NULL AND "ScopeVenue" IS NULL AND "ScopeSymbol" IS NULL)
                 OR ("Scope" = 5 AND "ScopeSymbol" IS NOT NULL AND "ScopeOperatingMode" IS NULL AND "ScopeVenue" IS NULL AND "ScopeBotId" IS NULL)
                )
                """);
        });

        #endregion
    }
}
