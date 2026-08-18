using System.ComponentModel.DataAnnotations;
using Mapster;
using CryptoSignal.Auth.Application.DTOs.Permissions;
using CryptoSignal.Infra.Tooling.Mapping.Conventions;

namespace CryptoSignal.Auth.Application.DTOs.Role;

public record RoleInputDto : IMapperRegister<RoleInputDto>, IValidatableObject
{
    public Guid Id { get; set; }
    public string Name { get; set; }

    public string Title { get; set; }
    public List<PermissionIdsDto> Permissions { get; set; }

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (string.IsNullOrWhiteSpace(Name))
            yield return new ValidationResult("وارد نمودن نام نقش اجباری است", [nameof(Name)]);
        else if (Name.Length > 100)
            yield return new ValidationResult("طول نام نقش حداکثر شامل 100 کارکتر می باشد", [nameof(Name)]);

        if (string.IsNullOrWhiteSpace(Title))
            yield return new ValidationResult("وارد نمودن عنوان نقش اجباری است", [nameof(Title)]);
        else if (Title.Length > 100)
            yield return new ValidationResult("طول عنوان نقش حداکثر شامل 100 کارکتر می باشد", [nameof(Title)]);

    }

    public void Register(TypeAdapterConfig config)
    {
        // config.NewConfig<RoleInputDto, Domain.Models.Role>()
        //     .Map(dest => dest.RolePermissions, 
        //         src => src.Permissions.Select(p => new RolePermission
        //         {
        //             PermissionId = p.Id
        //         }).ToList());
    }
}

public class RolesIdsDto
{
    public Guid Id { get; set; }
}