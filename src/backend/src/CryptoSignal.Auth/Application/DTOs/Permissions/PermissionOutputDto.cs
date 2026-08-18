using CryptoSignal.Infra.Base.API.DTO;
using CryptoSignal.Auth.Domain.Models;

namespace CryptoSignal.Auth.Application.DTOs.Permissions;

public class PermissionOutputDto :
    BaseOutputDto<Permission, PermissionOutputDto, Guid>
{
    public string Name { get; set; }
    public string Title { get; set; }
}
