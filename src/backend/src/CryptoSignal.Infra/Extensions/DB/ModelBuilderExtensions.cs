using System.Reflection;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Infra.Extensions.DB;

public static class ModelBuilderExtensions
{
    public static ModelBuilder ApplyModuleConfigurations(
        this ModelBuilder modelBuilder, params Assembly[] assemblies)
    {
        foreach (var asm in assemblies.Distinct())
            modelBuilder.ApplyConfigurationsFromAssembly(asm);
        return modelBuilder;
    }
    
    public static void RegisterEntities(this ModelBuilder modelBuilder, Assembly? assembly = null)
    {
        assembly ??= Assembly.GetExecutingAssembly();

        var entityTypes = assembly
            .GetExportedTypes()
            .Where(t =>
                t is { IsAbstract: false, IsInterface: false }
                && typeof(BaseEntity).IsAssignableFrom(t));

        foreach (var type in entityTypes)
            modelBuilder.Entity(type);
    }

    /// <summary>
    /// Maps <see cref="IEntityMarker.RowVersion"/> onto the PostgreSQL <c>xmin</c> system column for
    /// every mapped entity. Applied model-wide rather than in
    /// <see cref="BaseEntityTypeConfiguration{TEntity}"/> alone, because entities registered by
    /// reflection without an explicit configuration class would otherwise get a real
    /// <c>RowVersion</c> column that the database never populates.
    /// Call this after <c>ApplyModuleConfigurations</c>.
    /// </summary>
    public static ModelBuilder ConfigureXminConcurrencyTokens(this ModelBuilder modelBuilder)
    {
        foreach (var entityType in modelBuilder.Model.GetEntityTypes())
        {
            if (entityType.IsOwned()) continue;
            if (!typeof(IEntityMarker).IsAssignableFrom(entityType.ClrType)) continue;
            if (entityType.FindProperty(nameof(IEntityMarker.RowVersion)) is null) continue;

            modelBuilder.Entity(entityType.ClrType)
                .Property(nameof(IEntityMarker.RowVersion))
                .HasColumnName("xmin")
                .HasColumnType("xid")
                .ValueGeneratedOnAddOrUpdate()
                .IsConcurrencyToken();
        }

        return modelBuilder;
    }

    /// <summary>
    /// Gives every <see cref="decimal"/> property in the model an explicit precision and scale, unless
    /// a configuration already set one. Applied model-wide for the same reason as
    /// <see cref="ConfigureXminConcurrencyTokens"/>: completeness. A decimal mapped without precision
    /// falls back to the provider's default, and for money that silent default is a correctness bug the
    /// live-trading safety policy forbids. Sweeping the whole model means a monetary column cannot be
    /// added and then forgotten — it is impossible for one to reach the schema unscaled.
    /// </summary>
    /// <remarks>
    /// <paramref name="precision"/> 28 and <paramref name="scale"/> 10 span crypto's needs: up to
    /// eighteen integer digits (well past any quote notional) and ten fractional (past satoshi
    /// resolution). A property that genuinely needs different precision sets it in its own
    /// configuration and is skipped here, because an explicitly configured precision is left untouched.
    /// Call after <c>ApplyModuleConfigurations</c>.
    /// </remarks>
    public static ModelBuilder ConfigureDecimalPrecision(
        this ModelBuilder modelBuilder, int precision = 28, int scale = 10)
    {
        foreach (var entityType in modelBuilder.Model.GetEntityTypes())
        {
            foreach (var property in entityType.GetProperties())
            {
                var clrType = property.ClrType;
                if (clrType != typeof(decimal) && clrType != typeof(decimal?)) continue;
                if (property.GetPrecision() is not null) continue;

                property.SetPrecision(precision);
                property.SetScale(scale);
            }
        }

        return modelBuilder;
    }
}
