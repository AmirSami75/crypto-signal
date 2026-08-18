namespace CryptoSignal.Auth.Domain.Constants;

public static class AuthGlobalVariables
{
    public const string SuperAdminRole = "SuperAdmin";
    public const string UserRole = "User";

    /// <summary>
    /// Username of the bootstrap superadmin created by the seeder. This account is guarded against
    /// edit/delete/deactivate so the system can never be locked out of its own administration.
    /// </summary>
    public const string DefaultUser = "cs-admin";

    /// <summary>
    /// Fallback password for accounts created or reset through the admin UI. Every account created
    /// this way carries <c>RequirePasswordChange = true</c>.
    /// This is NOT used for the bootstrap superadmin — that password comes from configuration
    /// (<c>API_Settings:Bootstrap:SuperAdminPassword</c>) so a well-known credential never grants
    /// full administrative access.
    /// </summary>
    public const string DefaultPassword = "P@ssw0rd";

    public const int NumberOfWrongPasswordsAllowed = 5;
}
