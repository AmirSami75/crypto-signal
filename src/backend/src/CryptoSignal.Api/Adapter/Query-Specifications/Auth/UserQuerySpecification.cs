using CryptoSignal.Api.Application.DTOs.Auth;
using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Adapter.Query_Specifications.User;

namespace CryptoSignal.Api.Adapter.Query_Specifications.Auth;

/// <summary>
/// Search-filter expression builder for the user list. Inherits the base date-range handling for
/// <c>CreatedAt</c>; override <c>CreateFilters</c> here to add bespoke behaviour.
/// </summary>
public class UserQuerySpecification : BaseUserQuerySpecification<User, UserSearchDto>;
