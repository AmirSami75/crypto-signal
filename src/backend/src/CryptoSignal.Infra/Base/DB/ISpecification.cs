using System.Linq.Expressions;
using Microsoft.EntityFrameworkCore.Query;

namespace CryptoSignal.Infra.Base.DB;

public interface ISpecification<T>
{
    Expression<Func<T, bool>>? Criteria { get; }
    List<Expression<Func<T, object>>> Includes { get; }
    List<string> IncludePaths { get; }
    List<Func<IQueryable<T>, IQueryable<T>>> IncludeGraphs { get; }
    Func<IQueryable<T>, IOrderedQueryable<T>>? OrderBy { get; }
    int? Skip { get; }
    int? Take { get; }
    bool AsNoTracking { get; }
    bool AsSplitQuery { get; }
}