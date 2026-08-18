using Mapster;
using CryptoSignal.Infra.Base.API.Responses;

namespace CryptoSignal.Infra.Tooling.Mapping.Ports;

/// <summary>
/// Thin abstraction over Mapster to keep mapping concerns behind a stable boundary.
/// Designed to support:
///  - Simple object→object mapping
///  - In-place mapping into existing instances (EF-safe)
///  - Lists
///  - IQueryable projections for EF Core (server-side translation)
///  - DTO→DTO remapping helpers (single pass)
/// </summary>
public interface IMapperAdapter
{
    /// <summary>Map an object to a destination type.</summary>
    TDestination Map<TDestination>(object source);

    TDestination Map<TDestination>(object source, TypeAdapterConfig cfg);

    /// <summary>Map a typed source to a destination type.</summary>
    TDestination Map<TSource, TDestination>(TSource source);

    TDestination Map<TSource, TDestination>(TSource source, TypeAdapterConfig cfg);

    /// <summary>
    /// Map into an existing destination instance (safe for tracked EF entities).
    /// </summary>
    TDestination MapInto<TSource, TDestination>(TSource source, TDestination destination,
        TypeAdapterConfig? cfg = null);

    /// <summary>Map an enumerable to a concrete List of destination type.</summary>
    List<TDestination> MapList<TSource, TDestination>(IEnumerable<TSource> source);

    /// <summary>
    /// Project an EF IQueryable to IQueryable of destination type (server-side).
    /// Use this for SELECT-projections that translate to SQL.
    /// </summary>
    IQueryable<TDestination> ProjectTo<TSource, TDestination>(IQueryable<TSource> source);

    /// <summary>
    /// DTO→DTO remap (single pass). Useful when you want to apply Mapster rules between DTOs.
    /// </summary>
    T Remap<T>(T source) where T : class;

    /// <summary>DTO→DTO remap for a list (single pass).</summary>
    IList<T> RemapList<T>(IEnumerable<T> source) where T : class;

    /// <summary>DTO→DTO remap for a paged result (single pass).</summary>
    PagedResult<T> RemapPaged<T>(PagedResult<T> paged) where T : class;
}