using System.Linq.Expressions;

namespace CryptoSignal.Infra.Base.DB;

public class Spec<T> : ISpecification<T>
{
    public Expression<Func<T, bool>>? Criteria { get; set; }

    // supports: Includes = { x => x.Nav, x => x.OtherNav }
    public List<Expression<Func<T, object>>> Includes { get; } = new();

    // supports: IncludePaths = { "Cases.Profile", "IncomeInfos" }
    public List<string> IncludePaths { get; } = new();
    
    public List<Func<IQueryable<T>, IQueryable<T>>> IncludeGraphs { get; } = new();

    // supports: OrderBy = q => q.OrderBy(...)
    public Func<IQueryable<T>, IOrderedQueryable<T>>? OrderBy { get; set; }

    public int? Skip { get; set; }
    public int? Take { get; set; }

    public bool AsNoTracking { get; set; }
    public bool AsSplitQuery { get; set; }
}