using Mapster;
using MapsterMapper;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Tooling.Mapping.Ports;

namespace CryptoSignal.Infra.Tooling.Mapping.Adapters;

/// <summary>
/// Thin wrapper around Mapster's IMapper with a small set of convenience helpers.
/// Best-practice: one pass only; let Mapster’s config/attributes handle hooks.
/// </summary>
public sealed class MapperAdapter(IMapper mapper) : IMapperAdapter
{
    private readonly IMapper _mapper = mapper ?? throw new ArgumentNullException(nameof(mapper));

    // ---------- Public Mapping Methods ----------

    public TDestination Map<TDestination>(object source)
    {
        ArgumentNullException.ThrowIfNull(source);
        return _mapper.Map<TDestination>(source);
    }

    public TDestination Map<TDestination>(object source, TypeAdapterConfig cfg)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(cfg);
        return _mapper.From(source).Adapt<TDestination>(cfg);
    }

    public TDestination Map<TSource, TDestination>(TSource source)
    {
        ArgumentNullException.ThrowIfNull(source);
        return _mapper.Map<TDestination>(source!);
    }

    public TDestination Map<TSource, TDestination>(TSource source, TypeAdapterConfig cfg)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(cfg);
        return _mapper.From(source!).Adapt<TDestination>(cfg);
    }

    /// <summary>
    /// Maps source into an existing destination instance (safe for tracked EF entities).
    /// </summary>
    public TDestination MapInto<TSource, TDestination>(TSource source, TDestination destination,
        TypeAdapterConfig? cfg = null)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(destination);

        if (cfg is null) _mapper.Map(source!, destination!);
        else source!.Adapt(destination!, cfg);

        return destination!;
    }

    public List<TDestination> MapList<TSource, TDestination>(IEnumerable<TSource> source)
    {
        ArgumentNullException.ThrowIfNull(source);
        return _mapper.Map<List<TDestination>>(source);
    }

    /// <summary>
    /// Projects an IQueryable<TSource> to IQueryable<TDestination> using Mapster's ProjectToType.
    /// </summary>
    public IQueryable<TDestination> ProjectTo<TSource, TDestination>(IQueryable<TSource> source)
    {
        ArgumentNullException.ThrowIfNull(source);
        // Use the same config instance that IMapper was constructed with.
        return source.ProjectToType<TDestination>(_mapper.Config);
    }

    // ---------- DTO→DTO helpers (single pass) ----------

    public T Remap<T>(T source) where T : class
    {
        ArgumentNullException.ThrowIfNull(source);
        return _mapper.From(source).AdaptToType<T>();
    }

    public IList<T> RemapList<T>(IEnumerable<T> source) where T : class
    {
        ArgumentNullException.ThrowIfNull(source);
        return source.Select(s => _mapper.From(s).AdaptToType<T>()).ToList();
    }

    public PagedResult<T> RemapPaged<T>(PagedResult<T> paged) where T : class
    {
        ArgumentNullException.ThrowIfNull(paged);
        return new PagedResult<T>
        {
            Items = RemapList(paged.Items),
            TotalRecords = paged.TotalRecords,
            PageNumber = paged.PageNumber,
            PageSize = paged.PageSize,
        };
    }
}