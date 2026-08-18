using CryptoSignal.Auth.Application.DTOs.LoginHistory;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.API.SearchFilter;

namespace CryptoSignal.Auth.Adapter.Query_Specifications.User;

public class LoginHistoryQuerySpecification : ExpressionSearchFilterQuery<LoginHistory, LoginHistorySearchDto>
{
}