namespace CryptoSignal.Infra.Base.Auth;

public static class CryptoSignalClaimTypes
{
    public const string BranchId = "branch_id";
    public const string BranchName = "branch_name";
    public const string BranchCode = "branch_code";
    public const string SecurityStamp = "security_stamp";
    public const string IsSuperAdminUser = "super_admin";
    public const string IsParentUser = "parent_user";
    public const string NeedChangePassword = "need_change_pass";
    public const string NeedTwoFactorAuthentication = "need_2fa";
    public const string ClientIp = "client_ip";
    public const string Permissions = "permissions";
    public const string Roles = "permissions";
    public const string UserType = "user_type";
}