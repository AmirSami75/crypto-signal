using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Auth.Application.DTOs.Users;

public abstract  class BaseUserSearchDto
{
    [SearchFilter(ExpressionUtil.FilterTypes.Contains)]
    public string? UserName { get; set; }

    [SearchFilter(ExpressionUtil.FilterTypes.Contains)]
    public string? FullName { get; set; }

    [SearchFilter(ExpressionUtil.FilterTypes.Equal, true)]
    public string? CreatedAt { get; set; }

    [SearchFilter(ExpressionUtil.FilterTypes.Equal)]
    public bool? IsActive { get; set; }

    [SearchFilter(ExpressionUtil.FilterTypes.Equal)]
    public bool? IsLocked { get; set; }
}