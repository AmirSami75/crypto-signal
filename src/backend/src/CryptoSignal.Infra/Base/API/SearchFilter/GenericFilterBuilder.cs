using System.Reflection;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Helpers;

namespace CryptoSignal.Infra.Base.API.SearchFilter;

public static class GenericFilterBuilder
{
    public static List<ExpressionFilter> Build<TSearchDto>(TSearchDto dto)
        where TSearchDto : class
    {
        var filters = new List<ExpressionFilter>();
        if (dto == null) return filters;

        var props = typeof(TSearchDto).GetProperties();
        foreach (var prop in props)
        {
            var value = prop.GetValue(dto);
            if (value == null) continue;
            if (string.IsNullOrWhiteSpace(value.ToString())) continue;

            // Attribute support
            var attr = prop.GetCustomAttribute<SearchFilterAttribute>();
            var filterType = attr?.FilterType
                             ?? (prop.PropertyType == typeof(string)
                                 ? ExpressionUtil.FilterTypes.Contains
                                 : ExpressionUtil.FilterTypes.Equal);

            var operation = attr?.Operation ?? ExpressionUtil.QueryOperation.And;
            var propertyName = attr?.TargetProperty ?? prop.Name;
            var isCustomExoerssion = attr != null ? attr.IsCustomExpression : false;

            // IN query support: for lists/arrays
            if (value is System.Collections.IEnumerable enumerableValue &&
                !(value is string) &&
                filterType == ExpressionUtil.FilterTypes.In)
            {
                var list = new List<object>();
                foreach (var item in enumerableValue)
                    list.Add(item);

                if (!isCustomExoerssion)
                {
                    filters.Add(new ExpressionFilter
                    {
                        PropertyName = propertyName,
                        Value = list,
                        Comparison = filterType,
                        Operation = operation
                    });
                }

                continue;
            }

            if (!isCustomExoerssion)
            {
                filters.Add(new ExpressionFilter
                {
                    PropertyName = propertyName,
                    Value = value,
                    Comparison = filterType,
                    Operation = operation
                });
            }
        }

        return filters;
    }
}