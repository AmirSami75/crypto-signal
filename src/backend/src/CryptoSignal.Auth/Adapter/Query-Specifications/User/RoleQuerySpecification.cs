using CryptoSignal.Auth.Application.DTOs.Permissions;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.API.SearchFilter;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Auth.Adapter.Query_Specifications.User;

public class RoleQuerySpecification : ExpressionSearchFilterQuery<Role, RoleSearchDto>
{
}