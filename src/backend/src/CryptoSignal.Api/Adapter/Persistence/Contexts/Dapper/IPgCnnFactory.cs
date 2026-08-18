using System.Data;

namespace CryptoSignal.Api.Adapter.Persistence.Contexts.Dapper;

/// <summary>
/// Opens raw ADO.NET connections for Dapper-based reads that are impractical to express in LINQ.
/// EF Core remains the write path.
/// </summary>
public interface IPgCnnFactory
{
    Task<IDbConnection> CreateOpenConnectionAsync(CancellationToken ct = default);
}
