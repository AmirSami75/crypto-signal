using Mapster;
using Newtonsoft.Json;
using CryptoSignal.Infra.Base.Entity;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Extensions.Type;
using CryptoSignal.Infra.Tooling.Mapping.Conventions;

namespace CryptoSignal.Infra.Base.API.DTO;

public interface IOutputDto<TKey> where TKey : struct
{
    public TKey Id { get; set; }
    public string CreationDate { get; set; }
    public string? ModificationDate { get; set; }
    public string? UserCreatedName { get; set; }
    public string? UserLastUpdateName { get; set; }
}

public abstract class BaseOutputDto<TEntity, TOutputDto, TKey> :
    IOutputDto<TKey>,
    IMapperRegister<TOutputDto>
    where TKey : struct
    where TEntity : BaseEntity<TKey>
    where TOutputDto : BaseOutputDto<TEntity, TOutputDto, TKey>
{
    public TKey Id { get; set; }
    public string CreationDate { get; set; }
    public string CreationTime { get; set; }
    public string? ModificationDate { get; set; }
    public string? ModificationTime { get; set; }
    public string? UserCreatedName { get; set; }
    public string? UserLastUpdateName { get; set; }

    // Raw timestamps for EF-safe projection; not sent to clients
    [JsonIgnore] public DateTime CreatedAtRaw { get; set; }
    [JsonIgnore] public DateTime? UpdatedAtRaw { get; set; }


    public virtual void Register(TypeAdapterConfig config)
    {
        // 1) EF-safe projection: map raw DateTimes only (fully translatable)
        config.NewConfig<TEntity, TOutputDto>()
            .Map(dest => dest.CreatedAtRaw, s => s.CreatedAt)
            .Map(d => d.UpdatedAtRaw, s => s.UpdatedAt)
            .Map(d => d.UserCreatedName, s => s.UserCreatedName)
            .Map(d => d.UserLastUpdateName, s => s.UserLastUpdateName);

        // 2) Enrichment pass (DTO -> DTO): convert to Persian strings after materialization
        config.ForType<TOutputDto, TOutputDto>()
            .AfterMapping((src, dest) =>
            {
                dest.CreationDate = $"{src.CreatedAtRaw.ConvertToPersianDate(format: DateFormat.DateOnly)} {src.UserCreatedName}";
                dest.CreationTime = $"{src.CreatedAtRaw.ConvertToPersianDate(format: DateFormat.TimeOnly)} {src.UserCreatedName}";
                dest.ModificationDate = $"{src.UpdatedAtRaw?.ConvertToPersianDate(format: DateFormat.DateOnly)} {src.UserLastUpdateName}";
                dest.ModificationTime = $"{src.UpdatedAtRaw?.ConvertToPersianDate(format: DateFormat.TimeOnly)} {src.UserLastUpdateName}";
            });
    }
}