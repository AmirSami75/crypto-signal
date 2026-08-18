namespace CryptoSignal.Infra.Settings;

/// <summary>
/// Database configuration bound from <c>API_Settings:Db</c>.
/// Crypto Signal is PostgreSQL-only; <see cref="Type"/> is kept so the provider is explicit
/// in configuration and a wrong value fails fast at startup instead of silently using a default.
/// </summary>
public class DbSettings
{
    public const string PostgreSql = "PostgreSql";

    /// <summary>Provider discriminator. Only <c>PostgreSql</c> is supported.</summary>
    public string Type { get; set; } = PostgreSql;

    /// <summary>Npgsql connection string. Required.</summary>
    public string? PostgreSqlCnnStr { get; set; }

    /// <summary>Command timeout in seconds applied to the EF Core provider.</summary>
    public int CommandTimeoutSeconds { get; set; } = 30;

    /// <summary>
    /// Number of transient-failure retries performed by the Npgsql execution strategy. <c>0</c>
    /// disables retrying entirely, which is the default.
    /// <para>
    /// Raising this is not free: a retrying execution strategy cannot run inside a transaction the
    /// caller opened itself, and this codebase opens transactions in the user seeder and in the user
    /// and role controllers. Set this above zero only after wrapping every such transaction in
    /// <c>DbContext.Database.CreateExecutionStrategy()</c>.
    /// </para>
    /// </summary>
    public int MaxRetryCount { get; set; }

    /// <summary>Upper bound of the retry back-off in seconds.</summary>
    public int MaxRetryDelaySeconds { get; set; } = 10;
}
