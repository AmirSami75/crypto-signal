using CryptoSignal.Auth.Application.DTOs.Auth;
using CryptoSignal.Auth.Domain.Models;

namespace CryptoSignal.Auth.Application.Services.Contracts;

public interface IAuthService<TUserEntity> 
    where TUserEntity : BaseUser
{
    Task<TokenDto> GenerateToken(TUserEntity userEntity, string clientIp, bool mustChangePassword,string? userType = null);
    bool RequiresChangePassword(TUserEntity userEntity);
}