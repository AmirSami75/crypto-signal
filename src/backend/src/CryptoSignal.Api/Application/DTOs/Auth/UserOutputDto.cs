using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Auth.Application.DTOs.Users;
using CryptoSignal.Infra.Extensions.Type;
using Mapster;
using Newtonsoft.Json;

namespace CryptoSignal.Api.Application.DTOs.Auth;

/// <summary>
/// User projection returned by the user-management endpoints.
/// </summary>
public class UserOutputDto : BaseUserOutputDto<User, UserOutputDto>
{
    /// <summary>
    /// Carries the raw enum through the EF projection so the display name can be resolved in the
    /// second, in-memory remap pass — <c>ToDisplay()</c> has no SQL translation.
    /// </summary>
    [JsonIgnore]
    public Domain.Enums.Auth.UserType? UserTypeRaw { get; set; }

    public string? Mobile { get; set; }

    /// <summary>Human-readable <c>UserType</c>.</summary>
    public string? UserType { get; set; }

    public override void Register(TypeAdapterConfig config)
    {
        base.Register(config);

        config.ForType<User, UserOutputDto>()
            .Map(dest => dest.ParentId, src => src.ParentId)
            .Map(dest => dest.ParentName, src => src.ParentId != null ? src.Parent!.FullName : null)
            .Map(dest => dest.UserTypeRaw, src => src.UserType)
            .Ignore(dest => dest.UserType!)
            .Map(dest => dest.Roles, src => src.UserRoles != null
                ? src.UserRoles.Select(s => new RoleOutputDto
                {
                    Id = s.Role.Id,
                    Name = s.Role.Name,
                    Title = s.Role.Title
                })
                : null);

        config.ForType<UserOutputDto, UserOutputDto>()
            .AfterMapping((src, dest) => { dest.UserType = src.UserTypeRaw?.ToDisplay(); });
    }
}
