namespace CryptoSignal.Infra.Base.DB.AuditUser;

public class AuditLog
{
    public Guid? UserId { get; set; }
    public string? FullName { get; set; }
}