using Mapster;

namespace CryptoSignal.Auth.Application.DTOs.Auth;

public abstract class BaseSessionUserDto : IRegister
{
    public Guid UserId { get; set; }
    public string UserName { get; set; }
    public string FullName { get; set; }
    public string Token { get; set; }
    public DateTime TokenExpiry { get; set; }
    public bool IsSuperAdmin { get; set; }
    public bool IsParent { get; set; }
    public bool RequiresPasswordChange { get; set; }
    public List<Guid> Roles { get; set; }
    public List<string> Permissions { get; set; }

    /// <summary>
    /// Mapper Configuration you should override this method
    /// if you want to edit the base mapping for this DTO
    /// </summary>
    /// <param name="config"></param>
    public virtual void Register(TypeAdapterConfig config)
    {
        config.NewConfig<Domain.Models.BaseUser, BaseSessionUserDto>()
            .Map(dest => dest.UserId, src => src.Id)
            .Map(dest => dest.FullName, src => src.FullName)
            .Map(dest => dest.UserName, src => src.UserName)
            .Ignore(dest => dest.Token)
            .Ignore(dest => dest.TokenExpiry)
            .Ignore(dest => dest.IsSuperAdmin)
            .Ignore(dest => dest.IsParent)
            .Ignore(dest => dest.RequiresPasswordChange);
    }
}