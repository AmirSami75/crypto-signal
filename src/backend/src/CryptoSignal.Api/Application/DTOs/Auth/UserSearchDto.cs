using CryptoSignal.Api.Domain.Enums.Auth;
using CryptoSignal.Auth.Application.DTOs.Users;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Api.Application.DTOs.Auth;

/// <summary>
/// Search and filter criteria for the paged user list.
/// </summary>
public class UserSearchDto : BaseUserSearchDto
{
    [SearchFilter(ExpressionUtil.FilterTypes.Equal)]
    public string? PersonelCode { get; set; }

    [SearchFilter(ExpressionUtil.FilterTypes.Contains)]
    public string? Mobile { get; set; }

    [SearchFilter(ExpressionUtil.FilterTypes.Equal)]
    public UserType? UserType { get; set; }
}
