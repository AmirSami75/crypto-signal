using Mapster;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Infra.Base.API.DTO;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Auth.Application.DTOs.Users;

public abstract class BaseUserOutputDto<TEntity, TOutputDto> :
    BaseOutputDto<TEntity, TOutputDto, Guid>
    where TEntity : BaseEntity
    where TOutputDto : BaseOutputDto<TEntity, TOutputDto, Guid>
{
    public string FullName { get; set; }
    public string UserName { get; set; }
    public string? PersonelCode { get; set; }
    public string? Email { get; set; }
    public string? Phone { get; set; }
    public string? Address { get; set; }
    public bool IsActive { get; set; }
    public bool IsLocked { get; set; }
    public Guid? ParentId { get; set; }
    public string? ParentName { get; set; }
    public List<RoleOutputDto> Roles { get; set; }

    public override void Register(TypeAdapterConfig config)
    {
        base.Register(config);

        //Custom Mapping
    }
}