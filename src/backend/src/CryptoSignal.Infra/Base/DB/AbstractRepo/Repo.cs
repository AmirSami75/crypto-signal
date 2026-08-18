using System.Linq.Expressions;
using System.Reflection;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.ChangeTracking;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Entity;
using CryptoSignal.Infra.Extensions.DB;

namespace CryptoSignal.Infra.Base.DB.AbstractRepo;

public abstract class Repo<T>(DbContext dbContext) : IRepo<T> where T : BaseEntity
{
    public DbContext DbContext { get; } = dbContext;
    public virtual DbSet<T> Entities => DbContext.Set<T>();

    public virtual IQueryable<T> Table => Entities;
    public virtual IQueryable<T> TableNoTracking => Entities.AsNoTracking();

    #region Basic CRUD

    #region Fetch

    public virtual T? GetById(params object[] ids)
        => Entities.Find(ids);

    public virtual async ValueTask<T?> GetByIdAsync(CancellationToken cancellationToken, params object[] ids)
        => await Entities.FindAsync(ids, cancellationToken: cancellationToken);

    public virtual async Task<IReadOnlyList<T>> GetAllAsync(CancellationToken cancellationToken = default)
        => await Table.ToListAsync(cancellationToken);

    #endregion

    #region Add

    public virtual void Add(T entity, bool saveNow = true)
    {
        Entities.Add(entity);
        SaveIfNeeded(saveNow);
    }

    public virtual async Task AddAsync(T entity, bool saveNow = true, CancellationToken cancellationToken = default)
    {
        await Entities.AddAsync(entity, cancellationToken);
        await SaveIfNeededAsync(saveNow, cancellationToken);
    }

    public virtual void AddRange(IEnumerable<T> entities, bool saveNow = true)
    {
        Entities.AddRange(entities);
        SaveIfNeeded(saveNow);
    }

    public virtual async Task AddRangeAsync(IEnumerable<T> entities,
        bool saveNow = true, CancellationToken cancellationToken = default)
    {
        await Entities.AddRangeAsync(entities, cancellationToken);
        await SaveIfNeededAsync(saveNow, cancellationToken);
    }

    #endregion

    #region Update

    public virtual void Update(T entity, bool saveNow = true)
    {
        TouchUpdatedAt(entity);
        Entities.Update(entity);
        SaveIfNeeded(saveNow);
    }

    public virtual async Task UpdateAsync(T entity, bool saveNow = true, CancellationToken cancellationToken = default)
    {
        TouchUpdatedAt(entity);
        Entities.Update(entity);
        await SaveIfNeededAsync(saveNow, cancellationToken);
    }

    public virtual void UpdateRange(IEnumerable<T> entities, bool saveNow = true)
    {
        foreach (var e in entities) TouchUpdatedAt(e);
        Entities.UpdateRange(entities);
        SaveIfNeeded(saveNow);
    }

    public virtual async Task UpdateRangeAsync(IEnumerable<T> entities,
        bool saveNow = true, CancellationToken cancellationToken = default)
    {
        foreach (var e in entities) TouchUpdatedAt(e);
        Entities.UpdateRange(entities);
        await SaveIfNeededAsync(saveNow, cancellationToken);
    }

    #endregion

    #region Delete

    public virtual void SoftDelete(T entity, bool saveNow = true)
    {
        ApplySoftDelete(entity);
        SaveIfNeeded(saveNow);
    }

    public virtual async Task SoftDeleteAsync(T entity,
        bool saveNow = true, CancellationToken cancellationToken = default)
    {
        ApplySoftDelete(entity);
        await SaveIfNeededAsync(saveNow, cancellationToken);
    }

    public virtual void SoftDeleteRange(IEnumerable<T> entities, bool saveNow = true)
    {
        foreach (var e in entities) ApplySoftDelete(e);
        SaveIfNeeded(saveNow);
    }

    public virtual async Task SoftDeleteRangeAsync(IEnumerable<T> entities,
        bool saveNow = true,
        CancellationToken cancellationToken = default)
    {
        foreach (var e in entities) ApplySoftDelete(e);
        await SaveIfNeededAsync(saveNow, cancellationToken);
    }

    public virtual void HardDelete(T entity, bool saveNow = true)
    {
        Entities.Remove(entity);
        SaveIfNeeded(saveNow);
    }

    public virtual async Task HardDeleteAsync(T entity,
        bool saveNow = true, CancellationToken cancellationToken = default)
    {
        Entities.Remove(entity);
        await SaveIfNeededAsync(saveNow, cancellationToken);
    }

    public virtual void HardDeleteRange(IEnumerable<T> entities, bool saveNow = true)
    {
        Entities.RemoveRange(entities);
        SaveIfNeeded(saveNow);
    }

    public virtual async Task HardDeleteRangeAsync(IEnumerable<T> entities,
        bool saveNow = true,
        CancellationToken cancellationToken = default)
    {
        Entities.RemoveRange(entities);
        await SaveIfNeededAsync(saveNow, cancellationToken);
    }

    #endregion

    #endregion

    #region Attach/Detach & State

    public virtual void Attach(T entity)
        => Entities.Attach(entity);

    public virtual void Detach(T entity)
        => DbContext.Entry(entity).State = EntityState.Detached;

    public virtual EntityState GeTState(T entity)
        => DbContext.Entry(entity).State;

    #endregion

    #region Navigation Loading

    public virtual void LoadCollection<TProperty>(T entity,
        Expression<Func<T, IEnumerable<TProperty>>> collectionProperty)
        where TProperty : class
        => DbContext.Entry(entity).Collection(collectionProperty).Load();

    public virtual async Task LoadCollectionAsync<TProperty>(T entity,
        Expression<Func<T, IEnumerable<TProperty>>> collectionProperty, CancellationToken cancellationToken)
        where TProperty : class
        => await DbContext.Entry(entity).Collection(collectionProperty).LoadAsync(cancellationToken);

    public virtual void LoadReference<TProperty>(T entity, Expression<Func<T, TProperty>> referenceProperty)
        where TProperty : class
        => DbContext.Entry(entity).Reference(referenceProperty!).Load();

    public virtual async Task LoadReferenceAsync<TProperty>(T entity, Expression<Func<T, TProperty>> referenceProperty,
        CancellationToken cancellationToken)
        where TProperty : class
        => await DbContext.Entry(entity).Reference(referenceProperty!).LoadAsync(cancellationToken);

    #endregion

    #region Querying & Filtering

    public virtual IQueryable<T> Query(ISpecification<T> spec)
    {
        var query = spec.AsNoTracking ? TableNoTracking : Table;
        if (spec.Criteria is not null)
            query = query.Where(spec.Criteria);
        return query;
    }

    public virtual async Task<bool> ExistsAsync(
        ISpecification<T> spec,
        CancellationToken ct = default)
    {
        // Efficient Any(): apply filters & tracking flags only
        IQueryable<T> query = Table;
        query = Query(spec);
        if (spec.AsSplitQuery) query = query.AsSplitQuery();
        return await query.AnyAsync(ct);
    }

    public virtual async Task<int> CountAsync(
        ISpecification<T> spec,
        CancellationToken ct = default)
    {
        // Efficient Count(): apply filters & tracking flags only
        IQueryable<T> query = Table;
        query = Query(spec);
        if (spec.AsSplitQuery) query = query.AsSplitQuery();
        return await query.CountAsync(ct);
    }

    #endregion

    #region Advanced Fetching

    public virtual async Task<T?> FirstOrDefaultAsync(ISpecification<T> spec, CancellationToken ct = default)
    {
        IQueryable<T> query = Table.ApplySpec(spec);
        return await query.FirstOrDefaultAsync(ct);
    }

    public virtual async Task<T?> SingleOrDefaultAsync(ISpecification<T> spec, CancellationToken ct = default)
    {
        IQueryable<T> query = Table.ApplySpec(spec);
        return await query.SingleOrDefaultAsync(ct);
    }

    public virtual async Task<IReadOnlyList<T>> GetListAsync(ISpecification<T> spec, CancellationToken ct = default)
    {
        IQueryable<T> query = Table.ApplySpec(spec);
        return await query.ToListAsync(ct);
    }

    public virtual async Task<IReadOnlyList<TRes>> GetListAsync<TRes>(
        ISpecification<T> spec,
        Expression<Func<T, TRes>> selector,
        CancellationToken ct = default)
    {
        IQueryable<T> query = Table.ApplySpec(spec);
        return await query.Select(selector).ToListAsync(ct);
    }

    public IQueryable<T> TableWithDependencies(bool asNoTracking = false)
        => (asNoTracking ? TableNoTracking : Table).IncludeAll(DbContext);

    /// <summary>
    /// Expose IQueryable with the specification applied, to compose further outside the repo.
    /// </summary>
    public virtual IQueryable<T> TableWithSpec(ISpecification<T> spec)
        => Table.ApplySpec(spec);

    #endregion

    #region Pagination

    public virtual async Task<PagedResult<T>> GetPagedListAsync(
        ISpecification<T> spec,
        int pageNumber = 1,
        int pageSize = 20,
        CancellationToken ct = default)
    {
        if (pageNumber < 1) pageNumber = 1;
        if (pageSize < 1) pageSize = 20;

        IQueryable<T> query = Table.ApplySpec(spec);
        return await query.ToPagedResultAsync(pageNumber, pageSize, ct);
    }


    public virtual async Task<PagedResult<TRes>> GetPagedListAsync<TRes>(
        ISpecification<T> spec,
        Expression<Func<T, TRes>> selector,
        int pageNumber = 1,
        int pageSize = 20,
        CancellationToken ct = default) where TRes : class
    {
        if (pageNumber < 1) pageNumber = 1;
        if (pageSize < 1) pageSize = 20;

        IQueryable<T> query = Table.ApplySpec(spec);
        return await query.ToPagedResultAsync(selector, pageNumber, pageSize, ct);
    }

    #endregion

    #region Commit

    public virtual async Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
    {
        SetAuditFields();
        return await DbContext.SaveChangesAsync(cancellationToken);
    }


    public virtual async Task ExecuteInTransactionAsync(Func<CancellationToken, Task> action,
        CancellationToken ct = default)
    {
        // Use ambient transaction if present, otherwise create a new one
        var strategy = DbContext.Database.CreateExecutionStrategy();
        await strategy.ExecuteAsync(async () =>
        {
            await using var tx = await DbContext.Database.BeginTransactionAsync(ct);
            try
            {
                await action(ct);
                SetAuditFields();
                await DbContext.SaveChangesAsync(ct);
                await tx.CommitAsync(ct);
            }
            catch
            {
                await tx.RollbackAsync(ct);
                throw;
            }
        });
    }

    #endregion

    #region RawSQL

    public virtual IQueryable<T> FromSql(string sql, params object[] parameters)
        => Entities.FromSqlRaw(sql, parameters);

    public virtual async Task<List<TRes>> RawSqlQueryAsync<TRes>(string sql, object[]? parameters = null,
        CancellationToken cancellationToken = default) where TRes : class, new()
    {
        // If TRes is not an entity, ensure DbContext has DbSet<TRes> or EF Core 8's Database.SqlQuery<TRes> is used.
        var set = DbContext.Set<TRes>();
        var query = set.FromSqlRaw(sql, parameters ?? []);
        return await query.ToListAsync(cancellationToken);
    }

    // Execute non-query raw SQL (INSERT/UPDATE/DELETE)
    public virtual async Task<int> ExecuteSqlAsync(string sql, object[]? parameters = null,
        CancellationToken cancellationToken = default)
        => await DbContext.Database.ExecuteSqlRawAsync(sql, parameters ?? Array.Empty<object>(), cancellationToken);

    #endregion

    #region Helpers

    private void SaveIfNeeded(bool saveNow)
    {
        if (saveNow)
        {
            SetAuditFields();
            DbContext.SaveChanges();
        }
    }

    private async Task SaveIfNeededAsync(bool saveNow, CancellationToken ct)
    {
        if (saveNow)
        {
            SetAuditFields();
            await DbContext.SaveChangesAsync(ct);
        }
    }

    private void ApplySoftDelete(T entity)
    {
        // Convention-based soft delete:
        // - bool IsDeleted = true
        // - DateTime? DeletedAt = UtcNow
        var type = entity!.GetType();
        var isDeletedProp = type.GetProperty("IsDeleted",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        var updateAtProp =
            type.GetProperty("UpdateAt", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);

        if (isDeletedProp is { CanWrite: true } && isDeletedProp.PropertyType == typeof(bool))
            isDeletedProp.SetValue(entity, true);

        if (updateAtProp is { CanWrite: true } && (updateAtProp.PropertyType == typeof(DateTime?) ||
                                                   updateAtProp.PropertyType == typeof(DateTime)))
            updateAtProp.SetValue(entity, DateTime.UtcNow);

        DbContext.Entry(entity).State = EntityState.Modified;
    }

    private static readonly string[] UpdatedAtNames = ["UpdateAt", "UpdatedAt", "ModifiedAt", "LastUpdatedAt"];

    private void TouchUpdatedAt(object entity)
    {
        var type = entity.GetType();
        foreach (var name in UpdatedAtNames)
        {
            var pi = type.GetProperty(name,
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);

            if (pi is not { CanWrite: true } ||
                (pi.PropertyType != typeof(DateTime) && pi.PropertyType != typeof(DateTime?))) continue;
            pi.SetValue(entity, DateTime.UtcNow);
            return;
        }
    }

    #endregion

    #region Audit Fields

    private void SetAuditFields()
    {
        // Set CreatedAt for new entities
        foreach (var entry in DbContext.ChangeTracker.Entries<T>())
        {
            switch (entry.State)
            {
                case EntityState.Added:
                    SetCreatedAt(entry.Entity); // Set CreatedAt to DateTime.UtcNow
                    break;
                case EntityState.Modified:
                    SetUpdatedAt(entry.Entity); // Set UpdatedAt to DateTime.UtcNow
                    break;
            }
        }
    }

    private void SetCreatedAt(T entity)
    {
        var createdAtProp = entity.GetType().GetProperty("CreatedAt",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (createdAtProp != null && createdAtProp.CanWrite && createdAtProp.PropertyType == typeof(DateTime))
        {
            createdAtProp.SetValue(entity, DateTime.UtcNow);
        }
    }

    private void SetUpdatedAt(T entity)
    {
        var updatedAtProp = entity.GetType().GetProperty("UpdatedAt",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (updatedAtProp != null && updatedAtProp.CanWrite && updatedAtProp.PropertyType == typeof(DateTime))
        {
            updatedAtProp.SetValue(entity, DateTime.UtcNow);
        }
    }

    #endregion
}