using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.ChangeTracking;
using Microsoft.EntityFrameworkCore.Diagnostics;
using CryptoSignal.Infra.Base.DB.AuditUser;
using CryptoSignal.Infra.Base.Entity;
using CryptoSignal.Infra.Base.Markers;

namespace CryptoSignal.Infra.Base.DB.Interceptors;

public class AuditCurrentUserInterceptor(ICurrentUserCtx currentUserCtx) : SaveChangesInterceptor, IScopedInfraMarker
{
    public override InterceptionResult<int> SavingChanges(
        DbContextEventData eventData,
        InterceptionResult<int> result)
    {
        ApplyAuditInformation(eventData.Context);

        return result;
    }

    public override ValueTask<InterceptionResult<int>> SavingChangesAsync(
        DbContextEventData eventData,
        InterceptionResult<int> result,
        CancellationToken cancellationToken = default)
    {
        ApplyAuditInformation(eventData.Context);

        return ValueTask.FromResult(result);
    }

    private void ApplyAuditInformation(DbContext? dbContext)
    {
        if (dbContext is null)
            return;

        dbContext.ChangeTracker.DetectChanges();

        var now = DateTime.UtcNow;
        var userId = currentUserCtx.UserId;
        var userFullName = currentUserCtx.UserFullName ?? "System";

        var entries = dbContext.ChangeTracker
            .Entries<BaseEntity>()
            .Where(entry =>
                entry.State is EntityState.Added
                    or EntityState.Modified
                    or EntityState.Deleted)
            .ToList();

        foreach (var entry in entries)
        {
            switch (entry.State)
            {
                case EntityState.Added:
                    ApplyInsertAudit(
                        entry,
                        userId,
                        userFullName,
                        now);
                    break;

                case EntityState.Modified:
                    ApplyUpdateAudit(
                        entry,
                        userId,
                        userFullName,
                        now);
                    break;
            }
        }
    }

    private static void ApplyInsertAudit(
        EntityEntry<BaseEntity> entry,
        Guid? userId,
        string userFullName,
        DateTime now)
    {
        entry.Entity.CreatedAt = now;

        entry.Entity.UserCreatedId = userId;
        entry.Entity.UserCreatedName = userFullName;

        // These fields should be empty when inserting.
        entry.Entity.UserLastUpdatedId = null;
        entry.Entity.UserLastUpdateName = null;
        entry.Entity.UpdatedAt = null;
    }

    private static void ApplyUpdateAudit(
        EntityEntry<BaseEntity> entry,
        Guid? userId,
        string userFullName,
        DateTime now)
    {
        entry.Entity.UpdatedAt = now;
        entry.Entity.UserLastUpdatedId = userId;
        entry.Entity.UserLastUpdateName = userFullName;

        // Prevent creator information from being overwritten,
        // especially when DbContext.Update(entity) is used.
        entry.Property(nameof(BaseEntity.CreatedAt))
            .IsModified = false;

        entry.Property(nameof(BaseEntity.UserCreatedId))
            .IsModified = false;

        entry.Property(nameof(BaseEntity.UserCreatedName))
            .IsModified = false;
    }
}