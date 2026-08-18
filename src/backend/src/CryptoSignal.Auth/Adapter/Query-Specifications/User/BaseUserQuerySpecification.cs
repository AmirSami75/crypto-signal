using CryptoSignal.Auth.Application.DTOs.Users;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.API.SearchFilter;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Extensions.Type;
using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Auth.Adapter.Query_Specifications.User;

/// <summary>
/// You Should Inherit this Base Class if you want to implement the customize version of search query of concrete dto
/// </summary>
public abstract class BaseUserQuerySpecification<TEntity, TSearchDto> :
    ExpressionSearchFilterQuery<TEntity, TSearchDto>
    where TEntity : BaseUser
    where TSearchDto : BaseUserSearchDto
{

    protected override List<ExpressionFilter> CreateFilters(TSearchDto dto)
    {
        var filters = base.CreateFilters(dto);

        if (!string.IsNullOrWhiteSpace(dto.CreatedAt))
        {
            filters.Add(new ExpressionFilter
            {
                PropertyName = nameof(dto.CreatedAt),
                Value = dto.CreatedAt.ConvertToGregorianDate(),
                Comparison = ExpressionUtil.FilterTypes.GreaterThanOrEqual,
                Operation = ExpressionUtil.QueryOperation.And
            });
            filters.Add(new ExpressionFilter
            {
                PropertyName = nameof(dto.CreatedAt),
                Value = dto.CreatedAt.ConvertToGregorianDate('/', 23, 59, 59),
                Comparison = ExpressionUtil.FilterTypes.LessThanOrEqual,
                Operation = ExpressionUtil.QueryOperation.And
            });
        }

        return filters;
    }
}