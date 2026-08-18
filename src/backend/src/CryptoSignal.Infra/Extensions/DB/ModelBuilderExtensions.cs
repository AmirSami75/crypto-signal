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
}
