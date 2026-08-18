using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Auth.Application.DTOs.Permissions;

public record PermissionSearchDto
{
    [SearchFilter(ExpressionUtil.FilterTypes.Contains)]
    public string? Title { get; init; }
}
