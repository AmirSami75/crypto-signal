using System.Linq.Expressions;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Base.API.Responses;

namespace CryptoSignal.Infra.Base.DB.AbstractRepo;

public interface IRepo<T> where T : class
{
    #region Context & DbSet Access

    DbContext DbContext { get; }
    DbSet<T> Entities { get; }

    /// <summary>
    /// Tracked queryable (default EF Core behavior).
    /// </summary>
    IQueryable<T> Table { get; }

    /// <summary>
    /// Untracked queryable for read-only operations.
    /// </summary>
    IQueryable<T> TableNoTracking { get; }

    #endregion

    #region Basic CRUD

    #region Fetch

    T? GetById(params object[] ids);
    ValueTask<T?> GetByIdAsync(CancellationToken cancellationToken, params object[] ids);

    Task<IReadOnlyList<T>> GetAllAsync(CancellationToken cancellationToken = default);

    #endregion

    #region Add

    void Add(T entity, bool saveNow = true);
    Task AddAsync(T entity, bool saveNow = true, CancellationToken cancellationToken = default);
    void AddRange(IEnumerable<T> entities, bool saveNow = true);
    Task AddRangeAsync(IEnumerable<T> entities, bool saveNow = true, CancellationToken cancellationToken = default);

    #endregion

    #region Update

    void Update(T entity, bool saveNow = true);
    Task UpdateAsync(T entity, bool saveNow = true, CancellationToken cancellationToken = default);

    void UpdateRange(IEnumerable<T> entities, bool saveNow = true);
    Task UpdateRangeAsync(IEnumerable<T> entities, bool saveNow = true, CancellationToken cancellationToken = default);

    #endregion

    #region Delete

    void SoftDelete(T entity, bool saveNow = true);
    Task SoftDeleteAsync(T entity, bool saveNow = true, CancellationToken cancellationToken = default);
    void SoftDeleteRange(IEnumerable<T> entities, bool saveNow = true);

    Task SoftDeleteRangeAsync(IEnumerable<T> entities,
        bool saveNow = true, CancellationToken cancellationToken = default);

    void HardDelete(T entity, bool saveNow = true);
    Task HardDeleteAsync(T entity, bool saveNow = true, CancellationToken cancellationToken = default);
    void HardDeleteRange(IEnumerable<T> entities, bool saveNow = true);

    Task HardDeleteRangeAsync(IEnumerable<T> entities,
        bool saveNow = true, CancellationToken cancellationToken = default);

    #endregion

    #endregion

    #region Attach/Detach

    void Attach(T entity);
    void Detach(T entity);

    #endregion

    #region Entity State

    EntityState GeTState(T entity);

    #endregion

    #region Navigation Properties

    void LoadCollection<TProperty>(T entity, Expression<Func<T, IEnumerable<TProperty>>> collectionProperty)
        where TProperty : class;

    Task LoadCollectionAsync<TProperty>(T entity, Expression<Func<T, IEnumerable<TProperty>>> collectionProperty,
        CancellationToken cancellationToken)
        where TProperty : class;

    void LoadReference<TProperty>(T entity, Expression<Func<T, TProperty>> referenceProperty)
        where TProperty : class;

    Task LoadReferenceAsync<TProperty>(T entity, Expression<Func<T, TProperty>> referenceProperty,
        CancellationToken cancellationToken)
        where TProperty : class;

    #endregion

    #region Querying & Filtering

    IQueryable<T> Query(ISpecification<T> spec);

    Task<bool> ExistsAsync(ISpecification<T> spec, CancellationToken ct = default);

    Task<int> CountAsync(ISpecification<T> spec, CancellationToken ct = default);

    #endregion

    #region Advanced Fetching

    Task<T?> FirstOrDefaultAsync(ISpecification<T> spec, CancellationToken ct = default);

    Task<T?> SingleOrDefaultAsync(ISpecification<T> spec, CancellationToken ct = default);

    Task<IReadOnlyList<T>> GetListAsync(ISpecification<T> spec, CancellationToken ct = default);

    Task<IReadOnlyList<TRes>> GetListAsync<TRes>(ISpecification<T> spec, Expression<Func<T, TRes>> selector,
        CancellationToken ct = default);

    IQueryable<T> TableWithDependencies(bool asNoTracking = false);

    IQueryable<T> TableWithSpec(ISpecification<T> spec);

    #endregion

    #region Pagination

    Task<PagedResult<T>> GetPagedListAsync(
        ISpecification<T> spec,
        int pageNumber = 1,
        int pageSize = 20,
        CancellationToken ct = default);


    Task<PagedResult<TRes>> GetPagedListAsync<TRes>(
        ISpecification<T> spec,
        Expression<Func<T, TRes>> selector,
        int pageNumber = 1,
        int pageSize = 20,
        CancellationToken ct = default) where TRes : class;

    #endregion

    #region Commit

    Task<int> SaveChangesAsync(CancellationToken cancellationToken = default);
    Task ExecuteInTransactionAsync(Func<CancellationToken, Task> action, CancellationToken ct = default);

    #endregion

    #region RawSQL

    // Query entities by raw SQL(returns tracked entities)
    IQueryable<T> FromSql(string sql, params object[] parameters);

    // Query any type by raw SQL (projection, DTOs, etc)
    Task<List<TRes>> RawSqlQueryAsync<TRes>(string sql, object[]? parameters = null,
        CancellationToken cancellationToken = default) where TRes : class, new();

    // Execute non-query raw SQL (INSERT/UPDATE/DELETE)
    Task<int> ExecuteSqlAsync(string sql, object[]? parameters = null, CancellationToken cancellationToken = default);

    #endregion
}