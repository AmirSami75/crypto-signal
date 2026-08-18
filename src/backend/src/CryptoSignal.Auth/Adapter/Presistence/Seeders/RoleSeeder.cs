using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.DB;

namespace CryptoSignal.Auth.Adapter.Presistence.Seeders;

public sealed class RoleSeeder(IRoleRepo roleRepo) : IEntitySeedData
{
    public int Order => 4;

    public async Task SeedAsync()
    {
        if (!roleRepo.TableNoTracking.Any(p => p.Type == RoleType.SuperAdmin))
        {
            var superAdminRole = new Role
            {
                Name = "SuperAdmin",
                Title = "مدیر ارشد سیستم",
                Type = RoleType.SuperAdmin
            };
            await roleRepo.AddAsync(superAdminRole);
        }

        if (!roleRepo.TableNoTracking.Any(p => p.Type == RoleType.User))
        {
            var normalUserRole = new Role
            {
                Name = "User",
                Title = "کاربر عادی",
                Type = RoleType.User
            };
            await roleRepo.AddAsync(normalUserRole);
        }

    }
}