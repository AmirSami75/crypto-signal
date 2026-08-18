using CryptoSignal.Infra.Base.API.Responses;

namespace CryptoSignal.Infra.Extensions.Type;

public  static class ListExtensions
{
    /// <summary>
    /// Convert list to paged result
    /// </summary>
    public static PagedResult<T> ToPagedResult<T>(
        this List<T> source,
        int pageNumber,
        int pageSize)
        where T : class
    {
        /*
            Safety Guards
        */

        if (pageNumber <= 0)
            pageNumber = 1;

        if (pageSize <= 0)
            pageSize = 10;

        /*
            Materialize once
        */

        var data = source.ToList();

        /*
            Total count before pagination
        */

        var totalRecords = data.Count;

        /*
            Pagination
        */

        var items = data
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToList();

        /*
            Build result
        */

        return new PagedResult<T>(
            items,
            totalRecords,
            pageNumber,
            pageSize);
    }
}