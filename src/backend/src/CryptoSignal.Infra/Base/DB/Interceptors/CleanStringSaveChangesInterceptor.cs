using System.Collections.Concurrent;
using System.Reflection;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.ChangeTracking;
using Microsoft.EntityFrameworkCore.Diagnostics;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.Markers;
using CryptoSignal.Infra.Extensions.Contracts;

namespace CryptoSignal.Infra.Base.DB.Interceptors;

public class CleanStringSaveChangesInterceptor(IStringNormalizer normalizer)
    : SaveChangesInterceptor, ISingletonInfraMarker
{
    private static readonly ConcurrentDictionary<Type, PropertyInfo[]> _stringPropsCache = new();

    public override InterceptionResult<int> SavingChanges(DbContextEventData eventData, InterceptionResult<int> result)
    {
        NormalizeStrings(eventData.Context);
        return base.SavingChanges(eventData, result);
    }

    public override ValueTask<InterceptionResult<int>> SavingChangesAsync(
        DbContextEventData eventData, InterceptionResult<int> result, CancellationToken cancellationToken = default)
    {
        NormalizeStrings(eventData.Context);
        return base.SavingChangesAsync(eventData, result, cancellationToken);
    }

    private void NormalizeStrings(DbContext? context)
    {
        if (context is null) return;

        foreach (var entry in context.ChangeTracker.Entries()
                     .Where(e => e.State is EntityState.Added or EntityState.Modified))
        {
            var entity = entry.Entity;
            if (entity is null) continue;

            foreach (var prop in GetStringProps(entity.GetType()))
            {
                var current = (string?)prop.GetValue(entity);
                var normalized = normalizer.Normalize(current);

                // Only set if different to avoid dirtying unchanged entities
                if (!string.Equals(current, normalized, StringComparison.Ordinal))
                {
                    prop.SetValue(entity, normalized);
                    // Mark property as modified to ensure persistence if needed
                    if (entry.Property(prop.Name) is PropertyEntry pe)
                        pe.IsModified = true;
                }
            }
        }
    }

    private static PropertyInfo[] GetStringProps(Type type) =>
        _stringPropsCache.GetOrAdd(type, t =>
            t.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .Where(p =>
                    p.CanRead && p.CanWrite &&
                    p.PropertyType == typeof(string) &&
                    p.GetCustomAttribute<DoNotNormalizeAttribute>() is null)
                .ToArray());
}