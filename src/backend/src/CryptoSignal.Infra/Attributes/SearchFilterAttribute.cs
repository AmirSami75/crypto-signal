using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Infra.Attributes;

public class SearchFilterAttribute(ExpressionUtil.FilterTypes filterType, bool IsCustomExpression = false) : Attribute
{
    public bool IsCustomExpression { get; set; } = IsCustomExpression;
    public ExpressionUtil.FilterTypes FilterType { get; set; } = filterType;
    public ExpressionUtil.QueryOperation Operation { get; set; } = ExpressionUtil.QueryOperation.And;
    public string? TargetProperty { get; set; } // For navigation properties
}