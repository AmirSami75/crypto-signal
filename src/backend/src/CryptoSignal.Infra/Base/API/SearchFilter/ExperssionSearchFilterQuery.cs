using System.Linq.Expressions;
using CryptoSignal.Infra.Base.Entity;
using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Infra.Base.API.SearchFilter;

public abstract class ExpressionSearchFilterQuery<TEntity, TSearchDto>
    where TSearchDto : class
    where TEntity : IEntityMarker
{
    protected List<ExpressionFilter> ExpressionsList = new List<ExpressionFilter>();

    public Expression<Func<TEntity, bool>>? CreateSearchQueryFilter(TSearchDto dto)
    {
        var filters = CreateFilters(dto);
        return filters.Count == 0 ? _ => true : ExpressionUtil.ConstructExpressionTree<TEntity>(filters);
    }

    protected virtual List<ExpressionFilter> CreateFilters(TSearchDto dto)
    {
       return GenericFilterBuilder.Build(dto);
    }
}