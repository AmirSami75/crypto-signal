using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Auth.Application.DTOs.Role;

public record RoleSearchDto
{
    [SearchFilter(ExpressionUtil.FilterTypes.Contains)]
    public string? Title { get; init; }
}
