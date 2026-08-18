using Microsoft.EntityFrameworkCore;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Constants;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Exceptions.Common;

namespace CryptoSignal.Auth.Adapter.Presistence.Seeders;

public abstract class BaseUserSeeder<TUserEntity>(
    IBaseUserRepo<TUserEntity> repo,
    IRoleRepo roleRepo,
    IUserRoleRepo userRoleRepo) :
    IEntitySeedData
    where TUserEntity : BaseUser
{
    public int Order => 5;

    public virtual async Task SeedAsync()
    {
        // Routed through the execution strategy rather than opening the transaction directly. A
        // retrying strategy refuses to run inside a caller-opened transaction, so without this the
        // seeder throws on boot whenever API_Settings:Db:MaxRetryCount is above zero. With retrying
        // off the strategy is a pass-through and this costs nothing.
        var strategy = repo.DbContext.Database.CreateExecutionStrategy();

        await strategy.ExecuteAsync(async () =>
        {
            // Inside the delegate on purpose: a retried attempt has to re-read this, otherwise it
            // would insert the superadmin a second time after a partially applied first attempt.
            if (await repo.TableNoTracking.AnyAsync(p =>
                    p.UserName == AuthGlobalVariables.DefaultUser && !p.IsDeleted))
                return;

            await using var transaction = await repo.DbContext.Database.BeginTransactionAsync();
            try
            {
                var users = CreateDefaultUser();
                await repo.AddRangeAsync(users);

                // Get Default Systematic Role
                var superAdminRole = roleRepo.TableNoTracking.FirstOrDefault(p => p.Type == RoleType.SuperAdmin);
                if (superAdminRole is null)
                    throw new NotFoundException("اطلاعات نقش مدیر ارشد سیستم در پایگاه داده موجود نیست");

                // Add SuperAdmin UserRole
                var userRoles =
                    users.Select(user => new UserRole
                    {
                        RoleId = superAdminRole.Id,
                        UserId = user.Id,
                        CreatedAt = DateTime.UtcNow
                    }).ToList();

                await userRoleRepo.AddRangeAsync(userRoles);

                await transaction.CommitAsync();
            }
            catch (Exception)
            {
                await transaction.RollbackAsync();
                throw;
            }
        });
    }

    protected abstract List<TUserEntity> CreateDefaultUser();
}