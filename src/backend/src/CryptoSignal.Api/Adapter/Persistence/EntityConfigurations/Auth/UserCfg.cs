using CryptoSignal.Api.Domain.Models.Auth;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace CryptoSignal.Api.Adapter.Persistence.EntityConfigurations.Auth;

/// <summary>
/// Configuration for the Crypto Signal-specific columns on <see cref="User"/>.
/// </summary>
/// <remarks>
/// Everything declared on <c>BaseUser</c> (keys, lengths, defaults, the self-relationship, the
/// concurrency token and the unique-username index) is configured by the Auth module's
/// <c>BaseUserCfg</c>. <see cref="User"/> is a TPH descendant of that root, so this class only adds
/// what <see cref="User"/> itself declares — re-declaring inherited members here would fight the
/// base configuration.
/// </remarks>
public sealed class UserCfg : IEntityTypeConfiguration<User>
{
    public void Configure(EntityTypeBuilder<User> builder)
    {
        #region Properties

        builder.Property(x => x.Mobile).HasMaxLength(30).IsUnicode();

        // Persisted as its numeric value so renaming an enum member cannot reinterpret stored rows.
        builder.Property(x => x.UserType).HasConversion<int?>();

        #endregion

        #region Indexes

        builder.HasIndex(x => x.UserType)
            .HasDatabaseName("IX_Users_UserType");

        #endregion
    }
}
