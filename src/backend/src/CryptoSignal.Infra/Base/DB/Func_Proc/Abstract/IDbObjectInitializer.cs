using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Infra.Base.DB.Func_Proc.Abstract;

public interface IDbObjectInitializer
{
    /// <summary>Execution order (lower runs earlier).</summary>
    int Order { get; }

    /// <summary>Run custom initialization (functions, views, etc.).</summary>
    Task InitializeAsync(DbContext dbContext, CancellationToken ct = default);
}