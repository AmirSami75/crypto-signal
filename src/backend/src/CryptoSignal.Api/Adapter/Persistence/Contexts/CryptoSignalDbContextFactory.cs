using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace CryptoSignal.Api.Adapter.Persistence.Contexts;

/// <summary>
/// Builds a <see cref="CryptoSignalDbContext"/> for <c>dotnet ef</c> at authoring time only.
/// </summary>
/// <remarks>
/// <para>
/// The running app builds its context through <c>InjectDbContext&lt;T&gt;</c>, which resolves the
/// connection string <em>and</em> the audit / tracing interceptors out of the service graph. The EF
/// tooling has neither: it never starts the host, so asking it to resolve <c>DbSettings</c> or
/// <c>AuditCurrentUserInterceptor</c> from DI would fail before a migration could be written. This
/// factory is the design-time seam that sidesteps all of it — the interceptors are runtime behaviour
/// and contribute nothing to the schema, so a migration authored without them is identical to one
/// authored with them.
/// </para>
/// <para>
/// Migrations are generated from the model, never from a database: <c>migrations add</c> and
/// <c>migrations script</c> open no connection, so the string below need only be well-formed, not
/// reachable. A real host or a set <c>API_Settings__Db__PostgreSqlCnnStr</c> is still required for the
/// commands that <em>do</em> connect (<c>database update</c>, <c>migrations bundle</c>), which is why
/// the environment override is honoured first — running the tooling against a live database uses that
/// database, and only a bare <c>migrations add</c> falls through to the placeholder.
/// </para>
/// </remarks>
public sealed class CryptoSignalDbContextFactory : IDesignTimeDbContextFactory<CryptoSignalDbContext>
{
    // A syntactically valid Npgsql string that resolves nowhere. Present so `migrations add` — which
    // never connects — has a provider configured; deliberately not a real host, so a design-time
    // command cannot silently touch a developer's database by falling through to a default.
    private const string DesignTimeConnectionString =
        "Host=localhost;Port=5432;Database=crypto_signal_design_time;Username=design_time;Password=design_time";

    public CryptoSignalDbContext CreateDbContext(string[] args)
    {
        var connectionString =
            Environment.GetEnvironmentVariable("API_Settings__Db__PostgreSqlCnnStr");
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            connectionString = DesignTimeConnectionString;
        }

        var options = new DbContextOptionsBuilder<CryptoSignalDbContext>()
            .UseNpgsql(connectionString, npgsql =>
                npgsql.MigrationsHistoryTable("__EFMigrationsHistory"))
            .Options;

        return new CryptoSignalDbContext(options);
    }
}
