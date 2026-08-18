using System.Data;
using CryptoSignal.Infra.Base.API.Responses;
using Dapper;

namespace CryptoSignal.Infra.Extensions.DB;

public static class DapperExtensions
{
    /// <summary>
    /// Runs <paramref name="baseQuery"/> as a paged PostgreSQL query and returns the page together
    /// with the total row count.
    /// </summary>
    /// <remarks>
    /// <paramref name="baseQuery"/> is interpolated into SQL, so it must be a developer-authored
    /// query, never built from user input. Values belong in <paramref name="parameters"/>.
    /// The query needs its own ORDER BY: PostgreSQL does not guarantee a stable order across
    /// LIMIT/OFFSET pages without one.
    /// </remarks>
    public static async Task<PagedResult<T>> ToPagedResultAsync<T>(
        this IDbConnection connection,
        string baseQuery,
        object? parameters = null,
        int pageNumber = 1,
        int pageSize = 50,
        string? countQuery = null,
        CancellationToken ct = default) where T : class
    {
        if (pageNumber < 1) pageNumber = 1;
        if (pageSize < 1) pageSize = 1;

        // Drop a trailing ; so the query can be nested in a sub-select.
        baseQuery = baseQuery.Trim().TrimEnd(';');

        // PostgreSQL requires an alias on a derived table.
        countQuery ??= $"SELECT COUNT(1) FROM ({baseQuery}) AS count_q";

        var dp = new DynamicParameters(parameters);

        var totalRecords = await connection.ExecuteScalarAsync<int>(
            new CommandDefinition(
                countQuery,
                parameters: dp,
                commandType: CommandType.Text,
                cancellationToken: ct));

        dp.Add("_page_limit", pageSize);
        dp.Add("_page_offset", (pageNumber - 1) * pageSize);

        var paginatedQuery = $"""
                              SELECT page_q.*
                              FROM (
                                  {baseQuery}
                              ) AS page_q
                              LIMIT @_page_limit OFFSET @_page_offset
                              """;

        var items = await connection.QueryAsync<T>(
            new CommandDefinition(
                paginatedQuery,
                parameters: dp,
                commandType: CommandType.Text,
                cancellationToken: ct));

        return new PagedResult<T>(items.ToList(), totalRecords, pageNumber, pageSize);
    }
}
