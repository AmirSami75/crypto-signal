using Humanizer;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Infra.Extensions.DB;

public static class ModelBuilderPluralization
{
    public static void PluralizeRootTableNames(this ModelBuilder modelBuilder, string? schema = "dbo")
    {
        foreach (var entityType in modelBuilder.Model.GetEntityTypes())
        {
            // Only act on root types (TPH root or TPT root)
            if (entityType.BaseType != null) continue;

            var clrType = entityType.ClrType;
            if (clrType is null) continue;

            var baseName = clrType.Name;
            var trimmed = TrimLeadingBase(baseName); // "BaseUser" -> "User"
            var plural = Pluralize(trimmed); // "User" -> "Users"

            entityType.SetSchema(schema);
            entityType.SetTableName(plural);
        }
    }

    private static string TrimLeadingBase(string name)
        => name.StartsWith("Base", StringComparison.Ordinal) ? name[4..] : name;

    private static string Pluralize(string name)
        => name.Pluralize(inputIsKnownToBeSingular: false);
}