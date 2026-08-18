using Asp.Versioning;
using CryptoSignal.Api.Adapter.Query_Specifications.Auth;
using CryptoSignal.Api.Adapter.Repos.Contracts.Auth;
using CryptoSignal.Api.Application.DTOs.Auth;
using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Auth.API.Controllers.v1;
using CryptoSignal.Auth.Application.DTOs.Role;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.RulesEngine;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;

namespace CryptoSignal.Api.API.Controllers.v1.Core;

/// <summary>
/// User management: CRUD plus account activation, deactivation and password reset.
/// </summary>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("User", "کاربر")]
public class UserController(
    IUserRepo repo,
    IUserRoleRepo userRoleRepo,
    IMapperAdapter mapper,
    UserQuerySpecification searchFilter,
    ILoggerAdapter<UserController> logger,
    ICrudRuleExecutor<UserInputDto, User, Guid> crudRules)
    : BaseUserController<UserController, UserInputDto, UserOutputDto, UserSearchDto, User>(
        repo, userRoleRepo, mapper, searchFilter, logger, crudRules)
{
    // Held in an explicit field instead of being captured from the primary constructor: the same
    // instance is already forwarded to the base constructor, and capturing it too would duplicate
    // that state (CS9107). A field initializer reads the parameter without capturing it.
    private readonly IUserRoleRepo _userRoleRepo = userRoleRepo;

    /// <summary>
    /// Replaces the user's role assignments. Called inside the create/update transaction owned by
    /// the base controller, so it must not commit or open one of its own.
    /// </summary>
    protected override async Task AddUserRoles(Guid userId, List<RolesIdsDto> roleIds)
    {
        if (roleIds.Count == 0)
            return;

        var userRoles = roleIds
            .Select(role => new UserRole { UserId = userId, RoleId = role.Id })
            .ToList();

        await _userRoleRepo.AddRangeAsync(userRoles);
    }

    #region Hooks

    // Mapster maps by convention on matching names; UserType is projected explicitly so the
    // mapping stays correct if the DTO and entity property shapes ever diverge.

    protected override void BeforeCreate(UserInputDto dto, User entity, CancellationToken ct)
        => entity.UserType = dto.UserType;

    protected override void BeforeUpdate(UserInputDto dto, User entity, CancellationToken ct)
        => entity.UserType = dto.UserType;

    #endregion
}
