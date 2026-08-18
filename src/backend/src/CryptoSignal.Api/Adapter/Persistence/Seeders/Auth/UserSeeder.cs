using CryptoSignal.Api.Adapter.Repos.Contracts.Auth;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Domain.Enums.Auth;
using CryptoSignal.Api.Domain.Models.Auth;
using CryptoSignal.Auth.Adapter.Presistence.Seeders;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Constants;
using CryptoSignal.Infra.Extensions.Type;
using CryptoSignal.Infra.Helpers;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.Adapter.Persistence.Seeders.Auth;

/// <summary>
/// Creates the bootstrap superadmin on first run. Runs once — the base seeder is a no-op as soon as
/// an account with <see cref="AuthGlobalVariables.DefaultUser"/> exists.
/// </summary>
public sealed class UserSeeder(
    IUserRepo repo,
    IRoleRepo roleRepo,
    IUserRoleRepo userRoleRepo,
    IOptions<BootstrapSettings> bootstrap,
    IHostEnvironment env,
    ILoggerAdapter<UserSeeder> logger)
    : BaseUserSeeder<User>(repo, roleRepo, userRoleRepo)
{
    protected override List<User> CreateDefaultUser()
    {
        var settings = bootstrap.Value;

        return
        [
            new User
            {
                UserName = AuthGlobalVariables.DefaultUser,
                FullName = settings.SuperAdminFullName,
                Email = settings.SuperAdminEmail,
                Password = PasswordHasher.Hash(ResolveSuperAdminPassword(settings)),
                UserType = UserType.Administrator,
                IsActive = true,
                IsLocked = false,

                // The operator must replace the bootstrap password on first login.
                RequirePasswordChange = true,
            }
        ];
    }

    /// <summary>
    /// Resolves the bootstrap password from configuration, refusing to fall back to the
    /// source-tree default anywhere but Development.
    /// </summary>
    private string ResolveSuperAdminPassword(BootstrapSettings settings)
    {
        var configured = settings.SuperAdminPassword;

        if (!string.IsNullOrWhiteSpace(configured))
        {
            if (!configured.IsStrongPassword())
            {
                throw new InvalidOperationException(
                    $"{BootstrapSettings.SectionName}:SuperAdminPassword does not meet the password " +
                    "strength policy. Provide a stronger value and restart.");
            }

            logger.Info("Seeding superadmin '{0}' with the configured bootstrap password.",
                AuthGlobalVariables.DefaultUser);

            return configured;
        }

        if (!env.IsDevelopment())
        {
            throw new InvalidOperationException(
                $"{BootstrapSettings.SectionName}:SuperAdminPassword is required in the " +
                $"'{env.EnvironmentName}' environment. Set it via the " +
                "API_Settings__Bootstrap__SuperAdminPassword environment variable — refusing to " +
                "create a superadmin with a password that is published in the source tree.");
        }

        logger.Warning(
            "No bootstrap password configured; seeding superadmin '{0}' with the built-in development " +
            "default. Set {1}:SuperAdminPassword before deploying anywhere reachable.",
            AuthGlobalVariables.DefaultUser,
            BootstrapSettings.SectionName);

        return AuthGlobalVariables.DefaultPassword;
    }
}
