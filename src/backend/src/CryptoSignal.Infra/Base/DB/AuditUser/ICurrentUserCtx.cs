namespace CryptoSignal.Infra.Base.DB.AuditUser;

public interface ICurrentUserCtx
{
    Guid? UserId { get; }
    string? UserFullName { get; }
}