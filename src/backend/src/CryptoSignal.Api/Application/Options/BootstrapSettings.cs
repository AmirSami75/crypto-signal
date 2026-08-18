namespace CryptoSignal.Api.Application.Options;

/// <summary>
/// First-run bootstrap configuration, bound from <c>API_Settings:Bootstrap</c>.
/// </summary>
public sealed class BootstrapSettings
{
    public const string SectionName = "API_Settings:Bootstrap";

    /// <summary>
    /// Password for the seeded superadmin account. Supply it out of band — environment variable
    /// <c>API_Settings__Bootstrap__SuperAdminPassword</c> or a secret store — never in a committed
    /// appsettings file.
    /// </summary>
    /// <remarks>
    /// Outside Development the seeder refuses to create the superadmin without this value, rather
    /// than fall back to a password that is public knowledge in the source tree.
    /// </remarks>
    public string? SuperAdminPassword { get; init; }

    /// <summary>Display name for the seeded superadmin account.</summary>
    public string SuperAdminFullName { get; init; } = "System Administrator";

    /// <summary>Optional contact address for the seeded superadmin account.</summary>
    public string? SuperAdminEmail { get; init; }
}
