using System.Linq.Expressions;
using System.Reflection;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Base.API;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Infra.Extensions.DB;

public static class IQueryableExtensions
{
    public static async Task<PagedResult<T>> ToPagedResultAsync<T>(
        this IQueryable<T> query,
        int pageNumber,
        int pageSize,
        CancellationToken cancellationToken = default)
        where T : class
    {
        var totalRecords = await query.CountAsync(cancellationToken);

        var items = await query
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(cancellationToken);

        return new PagedResult<T>(items, totalRecords, pageNumber, pageSize);
    }

    /// <summary>
    /// Paginate with an EF-translatable projection selector.
    /// Counts on the source query, then applies projection to the paged slice.
    /// </summary>
    public static async Task<PagedResult<TDest>> ToPagedResultAsync<TSource, TDest>(
        this IQueryable<TSource> query,
        Expression<Func<TSource, TDest>> selector,
        int pageNumber,
        int pageSize,
        CancellationToken cancellationToken = default)
        where TSource : class
        where TDest : class
    {
        var totalRecords = await query.CountAsync(cancellationToken);

        var items = await query
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .Select(selector) // EF-safe projection here
            .ToListAsync(cancellationToken);

        return new PagedResult<TDest>(items, totalRecords, pageNumber, pageSize);
    }

    /// <summary>
    /// Convenience to transform items of a paged result (e.g., run Mapster AfterMapping in-memory).
    /// </summary>
    public static PagedResult<TOut> MapItems<TIn, TOut>(
        this PagedResult<TIn> source,
        Func<IEnumerable<TIn>, List<TOut>> map)
        where TIn : class
        where TOut : class
    {
        var mapped = map(source.Items);
        return new PagedResult<TOut>(mapped, source.TotalRecords, source.PageNumber, source.PageSize);
    }

    public static IQueryable<T> OrderByDynamic<T>(this IQueryable<T> source, string property)
    {
        return ApplyOrder<T>(source, property, "OrderBy");
    }

    public static IQueryable<T> OrderByDescendingDynamic<T>(this IQueryable<T> source, string property)
    {
        return ApplyOrder<T>(source, property, "OrderByDescending");
    }

    private static IQueryable<T> ApplyOrder<T>(IQueryable<T> source, string property, string methodName)
    {
        if (string.IsNullOrWhiteSpace(property))
            throw new ArgumentNullException(nameof(property));

        var props = property.Split('.');
        var type = typeof(T);
        var arg = Expression.Parameter(type, "x");
        Expression expr = arg;

        foreach (var prop in props)
        {
            var pi = type.GetProperty(prop,
                BindingFlags.IgnoreCase | BindingFlags.Public | BindingFlags.Instance)!;
            if (pi == null)
                throw new ArgumentException($"Property '{prop}' does not exist on type '{type.Name}'.");

            expr = Expression.Property(expr, pi);
            type = pi.PropertyType;
        }

        LambdaExpression lambda = Expression.Lambda(expr, arg);
        object result = typeof(Queryable).GetMethods().Single(m => m.Name == methodName
                                                                   && m.IsGenericMethodDefinition
                                                                   && m.GetGenericArguments().Length == 2
                                                                   && m.GetParameters().Length == 2)
            .MakeGenericMethod(typeof(T), type)
            .Invoke(null, [source, lambda])!;

        return (IQueryable<T>)result;
    }

    /// <summary>
    /// Includes all reference and collection navigation properties for an entity.
    /// </summary>
    public static IQueryable<T> IncludeAll<T>(this IQueryable<T> query, DbContext context) where T : class
    {
        var entityType = context.Model.FindEntityType(typeof(T));
        if (entityType == null) return query;

        // Include reference navigations
        query =
            entityType
                .GetNavigations()
                .Aggregate(query, (current, nav) => current.Include(nav.Name));

        // Include skip navigations (many-to-many)

        return
            entityType
                .GetSkipNavigations()
                .Aggregate(query, (current, nav) => current.Include(nav.Name));
    }

    public static IQueryable<T> ApplySpec<T>(this IQueryable<T> query, ISpecification<T> spec) where T : class
    {
        if (spec.Criteria != null)
            query = query.Where(spec.Criteria);

        foreach (var include in spec.Includes)
            query = query.Include(include);
        
        foreach (var path in spec.IncludePaths)
            query = query.Include(path);
        
        foreach (var graph in spec.IncludeGraphs)
            query = graph(query);

        if (spec.AsNoTracking)
            query = query.AsNoTracking();

        if (spec.AsSplitQuery)
            query = query.AsSplitQuery();

        if (spec.OrderBy != null)
            query = spec.OrderBy(query);

        if (spec.Skip.HasValue) query = query.Skip(spec.Skip.Value);
        if (spec.Take.HasValue) query = query.Take(spec.Take.Value);

        return query;

    }
}