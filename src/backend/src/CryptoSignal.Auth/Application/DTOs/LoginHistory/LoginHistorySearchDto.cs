using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Auth.Application.DTOs.LoginHistory;

public record LoginHistorySearchDto
{
    [SearchFilter(ExpressionUtil.FilterTypes.Contains)]
    public string? IP { get; init; }
}
