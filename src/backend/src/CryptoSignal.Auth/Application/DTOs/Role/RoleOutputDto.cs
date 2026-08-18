using Mapster;
using CryptoSignal.Auth.Application.DTOs.Permissions;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.API.DTO;
using CryptoSignal.Infra.Extensions.Type;

namespace CryptoSignal.Auth.Application.DTOs.Role;

public class RoleOutputDto :
    BaseOutputDto<Domain.Models.Role, RoleOutputDto, Guid>
{
    public string Name { get; set; }
    public string Title { get; set; }
    public string Type { get; set; }
    public List<PermissionOutputDto> Permissions { get; set; }

    public override void Register(TypeAdapterConfig config)
    {
        base.Register(config);

        config.ForType<Domain.Models.Role, RoleOutputDto>()
            .Map(dest => dest.Name, src => src.Name)
            .Map(dest => dest.Title, src => src.Title)
            .Map(dest => dest.Type, src => src.Type.ToDisplay(DisplayProperty.Description))
            .Map(dest => dest.Permissions,
                src => src.RolePermissions
                    .Select(rp => new PermissionOutputDto
                    {
                        Id = rp.Permission!.Id,
                        Name = rp.Permission!.Name,
                        Title = rp.Permission!.Title,
                    })
                    .ToList());
    }
}