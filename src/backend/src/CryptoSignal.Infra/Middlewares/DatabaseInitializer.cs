using Microsoft.AspNetCore.Builder;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Base.DB.Func_Proc.Abstract;

namespace CryptoSignal.Infra.Middlewares;

public static class DatabaseInitializer
{
    public static async Task<IApplicationBuilder> UseDatabaseInitialization<TContext>(
        this IApplicationBuilder app,
        Func<IServiceProvider, CancellationToken, Task>? afterDatabaseCreated = null)
        where TContext : DbContext
    {
        var logger = app.ApplicationServices.GetRequiredService<ILogger<TContext>>();

        using var scope = app.ApplicationServices.CreateScope();
        var dbContext = scope.ServiceProvider.GetRequiredService<TContext>();

        logger.LogInformation("Starting database initialization for {DbContext}...", typeof(TContext).Name);

        try
        {
            // MigrateAsync, not EnsureCreatedAsync: the latter is a no-op on a database that already
            // exists, so a new entity would never reach the running dev DB. Migrating applies every
            // pending migration in order and bootstraps __EFMigrationsHistory on a fresh database. An
            // existing database predating migrations must have the Baseline row inserted as already
            // applied (see docs) so its live Auth tables are not re-created underneath it.
            logger.LogInformation("Applying database migrations...");
            await dbContext.Database.MigrateAsync();
            logger.LogInformation("Database migrations are up to date.");

            var customInitializers = scope.ServiceProvider
                .GetServices<IDbObjectInitializer>()
                .OrderBy(i => i.Order)
                .ToList();

            foreach (var initializer in customInitializers)
            {
                logger.LogInformation("Running custom DB initializer {Initializer}...", initializer.GetType().Name);
                await initializer.InitializeAsync(dbContext, CancellationToken.None);
            }

            // Branch Sync Initialize 
            if (afterDatabaseCreated is not null)
            {
                logger.LogInformation("Running post database initialization action...");
                await afterDatabaseCreated(scope.ServiceProvider, CancellationToken.None);
            }

            // Seed the DB
            var seeders =
                scope.ServiceProvider
                    .GetServices<IEntitySeedData>()
                    .OrderBy(s => s.Order)
                    .ToList();

            foreach (var seeder in seeders)
            {
                logger.LogInformation("Seeding data with {Seeder}...", seeder.GetType().Name);
                await seeder.SeedAsync();
            }

            logger.LogInformation("Database initialization completed for {DbContext}.", typeof(TContext).Name);
            return app;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Database migration failed.");
            throw;
        }
    }
}