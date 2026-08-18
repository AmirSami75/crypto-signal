using CryptoSignal.Api.Domain;
using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Domain;
using CryptoSignal.Infra.Extensions.DB;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.Adapter.Persistence.Contexts;

/// <summary>
/// PostgreSQL context for the Crypto Signal platform.
/// </summary>
public class CryptoSignalDbContext(DbContextOptions<CryptoSignalDbContext> opts) : DbContext(opts)
{
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        // Discover entities declared in this assembly (User and anything added later).
        modelBuilder.RegisterEntities(typeof(User).Assembly);

        // Apply IEntityTypeConfiguration classes from the Auth module and this project.
        modelBuilder.ApplyModuleConfigurations(
            typeof(IAuthMarker).Assembly,
            typeof(IApiMarker).Assembly
        );

        // PostgreSQL has a public default schema, so no schema is set explicitly.
        modelBuilder.PluralizeRootTableNames(schema: null);

        // Point every RowVersion at the xmin system column. Must run after the configurations
        // above so it also covers entities registered by reflection without a config class.
        modelBuilder.ConfigureXminConcurrencyTokens();

        base.OnModelCreating(modelBuilder);
    }
}
