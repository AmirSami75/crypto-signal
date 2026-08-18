using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using Newtonsoft.Json;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Adapter.Repos.Implementations;
using CryptoSignal.Auth.Application.DTOs.Auth;
using CryptoSignal.Auth.Application.Services.Contracts;
using CryptoSignal.Auth.Domain.Constants;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.Auth;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Settings;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Elastic.CommonSchema;

namespace CryptoSignal.Auth.Application.Services.Implementations;

public class AuthService<TUserEntity>(
    IOptionsSnapshot<JwtSettings> jwtSettings,
    IBaseUserRepo<TUserEntity> repo,
    IPermissionRepo permissionRepo,
    IRolePermissionRepo rolePermissionRepo) : IAuthService<TUserEntity>
    where TUserEntity : BaseUser
{
    private readonly JwtSettings _jwt = jwtSettings.Value;

    public async Task<TokenDto> GenerateToken(TUserEntity userEntity, string clientIp, bool mustChangePassword,
        string? userType = null)
    {
        try
        {
            var secretKey = Encoding.UTF8.GetBytes(_jwt.SecretKey);
            var signingCredentials = new SigningCredentials(new SymmetricSecurityKey(secretKey),
                SecurityAlgorithms.HmacSha256Signature);

            var isParentUser = await IsParentUser(userEntity.Id);
            var claims = GetClaims(userEntity, clientIp, mustChangePassword, isParentUser, userType);
            var descriptor = new SecurityTokenDescriptor
            {
                Issuer = _jwt.Issuer,
                Audience = _jwt.Audience,
                IssuedAt = DateTime.UtcNow,
                NotBefore = DateTime.UtcNow.AddMinutes(_jwt.NotBeforeMinutes),
                Expires = DateTime.UtcNow.AddMinutes(_jwt.ExpirationMinutes),
                SigningCredentials = signingCredentials,
                //EncryptingCredentials = encryptingCredentials,
                Subject = new ClaimsIdentity(claims),
            };

            var tokenHandler = new JwtSecurityTokenHandler();
            var securityToken = tokenHandler.CreateToken(descriptor);
            var jwt = tokenHandler.WriteToken(securityToken);
            return new TokenDto(jwt, descriptor.Expires.Value);
        }
        catch (Exception exp)
        {
            throw new LogicException("خطا در ورود به سامانه", exp);
        }
    }

    public bool RequiresChangePassword(TUserEntity userEntity)
    {
        return userEntity.LastPasswordChangedAt switch
        {
            null when userEntity.RequirePasswordChange => true,
            null when !userEntity.RequirePasswordChange => false,
            _ => (DateTime.UtcNow - userEntity.LastPasswordChangedAt.Value).TotalDays >= 120
        };
    }


    #region private methods

    private IEnumerable<Claim> GetClaims(BaseUser user, string clientIp, bool needChangePassword, bool isParentUser,
        string? userType = null)
    {
        var claims = new List<Claim>
        {
            new(ClaimTypes.Name, user.UserName),
            new(ClaimTypes.NameIdentifier, user.Id.ToString()),
            new(ClaimTypes.GivenName.ToString(), user.FullName),
            new(CryptoSignalClaimTypes.SecurityStamp, user.SecurityStamp.ToString()),
            new(CryptoSignalClaimTypes.ClientIp, clientIp),
            new(CryptoSignalClaimTypes.NeedChangePassword, needChangePassword.ToString()),
            new(CryptoSignalClaimTypes.BranchName, user.BranchName ?? string.Empty),
            new(CryptoSignalClaimTypes.BranchCode, user.BranchCode ?? string.Empty)
        };

        if (!string.IsNullOrWhiteSpace(userType))
            claims.Add(new Claim(CryptoSignalClaimTypes.UserType, userType));

        var isElevatedUser = false;
        List<Guid> roleIds = new List<Guid>();
        foreach (var userRole in user.UserRoles)
        {
            roleIds.Add(userRole.RoleId);
            if (userRole?.Role?.Type == RoleType.SuperAdmin)
                isElevatedUser = true;
        }

        claims.Add(new Claim(CryptoSignalClaimTypes.IsSuperAdminUser, isElevatedUser.ToString()));
        claims.Add(new Claim(CryptoSignalClaimTypes.IsParentUser, isParentUser.ToString()));
        claims.Add(new Claim(ClaimTypes.Role, JsonConvert.SerializeObject(roleIds)));

        // NOTE: We dont need this anymore cuase that bug for huge jwt buffer size on payload when give a role up to +10 permissions
        // claims.Add(new Claim(CryptoSignalClaimTypes.Permissions,
        //     JsonConvert.SerializeObject(GetPermissionsFromRoleIds(roleIds))));

        return claims;
    }

    private async Task<bool> IsParentUser(Guid userId)
        => await repo.TableNoTracking.AnyAsync(p => p.ParentId == userId);

    private string GetPermissionsFromRoleIds(IEnumerable<Guid> roleIds)
    {
        var permissions = roleIds
            .Select(roleId =>
                (from pr in rolePermissionRepo.TableNoTracking
                    join p in permissionRepo.TableNoTracking on pr.PermissionId equals p.Id
                    where pr.RoleId == roleId
                    select p.Name)
                .ToArray())
            .SelectMany(permissionNames => permissionNames)
            .Aggregate("", (current, permissionName) => current + $"{permissionName},");
        return permissions;
    }

    #endregion
}