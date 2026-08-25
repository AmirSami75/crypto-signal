using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Trading;

/// <summary>
/// Per-user exchange API credentials, sealed at rest.
/// </summary>
/// <remarks>
/// The ciphertext columns are sized for AES-GCM output of realistic key lengths plus nonce and tag,
/// base64-encoded. There is deliberately no plaintext column to "temporarily" hold a secret: the only
/// place a credential is ever in the clear is inside <c>SecretProtector.Open</c>'s return value, in
/// memory, for the duration of one signed request.
/// </remarks>
public sealed class ExchangeConnectionCfg : BaseEntityTypeConfiguration<ExchangeConnection>
{
    public override void Configure(EntityTypeBuilder<ExchangeConnection> builder)
    {
        base.Configure(builder);

        builder.HasKey(x => x.Id);
        builder.Property(x => x.Id)
            .ValueGeneratedOnAdd()
            .HasValueGenerator<GuidV7ValueGenerator>();

        #region Properties

        builder.Property(x => x.Label).HasMaxLength(100);
        builder.Property(x => x.ApiKeyEncrypted).HasMaxLength(512).IsUnicode(false);
        builder.Property(x => x.ApiSecretEncrypted).HasMaxLength(512).IsUnicode(false);
        builder.Property(x => x.KeyPreview).HasMaxLength(8).IsUnicode(false);

        builder.Property(x => x.Venue).HasConversion<int>();

        #endregion

        #region Indexes

        // Credential resolution runs on every tick of every bot: owner + venue + active must be an
        // index seek. Uniqueness is deliberately not enforced — a user may hold several connections
        // for one venue (main and sub-account) and pin bots to them individually.
        builder.HasIndex(x => new { x.UserId, x.Venue, x.IsActive })
            .HasDatabaseName("IX_ExchangeConnections_UserId_Venue_IsActive");

        #endregion
    }
}
