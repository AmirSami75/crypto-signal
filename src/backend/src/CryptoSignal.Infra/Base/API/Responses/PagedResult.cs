namespace CryptoSignal.Infra.Base.API.Responses;

public class PagedResult<T> where T : class
{
    public int TotalRecords { get; set; }
    public IList<T> Items { get; set; } = [];
    public int PageNumber { get; set; }
    public int PageSize { get; set; }
    
    public int Count => Items?.Count ?? 0;

    public PagedResult()
    {
    }

    public PagedResult(List<T> items, int totalRecords, int pageNumber, int pageSize)
    {
        Items = items ?? [];
        TotalRecords = totalRecords;
        PageNumber = pageNumber;
        PageSize = pageSize;
    }
}