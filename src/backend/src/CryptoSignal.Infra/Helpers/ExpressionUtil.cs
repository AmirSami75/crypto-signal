using System.ComponentModel;
using System.Linq.Expressions;
using System.Reflection;
using static CryptoSignal.Infra.Helpers.ExpressionUtil;

namespace CryptoSignal.Infra.Helpers;

public class ExpressionUtil
{
    public enum FilterTypes
    {
        Equal,
        LessThan,
        LessThanOrEqual,
        GreaterThan,
        GreaterThanOrEqual,
        NotEqual,
        Contains, //for strings  
        StartsWith, //for strings  
        EndsWith, //for strings
        In //for lists
    }

    public enum QueryOperation
    {
        And,
        Or
    }

    public static Expression<Func<T, bool>> ConstructExpressionTree<T>(List<ExpressionFilter> filters)
    {
        if (filters.Count == 0)
            return null;

        var param = Expression.Parameter(typeof(T), "t");
        Expression exp = null;

        if (filters.Count == 1)
        {
            exp = ExpressionRetriever.GetExpression<T>(param, filters[0]);
        }
        else
        {
            exp = ExpressionRetriever.GetExpression<T>(param, filters[0]);
            for (var i = 1; i < filters.Count; i++)
                if (filters[i].Operation == QueryOperation.And)
                    exp = Expression.And(exp, ExpressionRetriever.GetExpression<T>(param, filters[i]));
                else
                    exp = Expression.Or(exp, ExpressionRetriever.GetExpression<T>(param, filters[i]));
        }


        return Expression.Lambda<Func<T, bool>>(exp, param);
    }

    #region Old - Code
    //
    // public static Expression<Func<T, bool>> ConstructDynamicExpressionTree<T>(List<ExpressionFilter> filters)
    // {
    //     if (filters.Count == 0)
    //         return null;
    //
    //     var param = Expression.Parameter(typeof(T), "t");
    //     Expression expMain = null;
    //     Expression expToAdd = null;
    //     Expression expressionPriority = null;
    //
    //     if (filters.Count == 1)
    //     {
    //         expMain = ExpressionRetriever.GetExpression<T>(param, filters[0]);
    //     }
    //     else
    //     {
    //         expMain = ExpressionRetriever.GetExpression<T>(param, filters[0]);
    //         //  Add exprission Or and And and
    //
    //         for (var i = 1; i < filters.Count; i++)
    //         {
    //             expToAdd = ExpressionRetriever.GetExpression<T>(param, filters[i]);
    //             if (filters[i - 1].Operation == QueryOperation.And)
    //             {
    //                 expMain = Expression.And(expMain, expToAdd);
    //             }
    //             else
    //             {
    //                 expMain = Expression.Or(expMain, expToAdd);
    //             }
    //         }
    //     }
    //
    //
    //     return Expression.Lambda<Func<T, bool>>(expMain, param);
    // }
    //
    // public static Expression ConstructDynamicExpressionTreeSeparate<T>(List<ExpressionFilter> filters,
    //     ParameterExpression param, bool hasInclude = false)
    // {
    //     if (filters.Count == 0)
    //         return null;
    //
    //     //  var param = Expression.Parameter(typeof(T), "c");
    //     Expression expMain = null;
    //     Expression expToAdd = null;
    //     Expression expressionPriority = null;
    //
    //     if (filters.Count == 1)
    //     {
    //         expMain = ExpressionRetriever.GetExpression<T>(param, filters[0], hasInclude);
    //     }
    //     else
    //     {
    //         expMain = ExpressionRetriever.GetExpression<T>(param, filters[0], hasInclude);
    //         //  Add exprission Or and And and
    //
    //         for (var i = 1; i < filters.Count; i++)
    //         {
    //             expToAdd = ExpressionRetriever.GetExpression<T>(param, filters[i], hasInclude);
    //             if (filters[i - 1].Operation == QueryOperation.And)
    //             {
    //                 expMain = Expression.And(expMain, expToAdd);
    //             }
    //             else
    //             {
    //                 expMain = Expression.Or(expMain, expToAdd);
    //             }
    //         }
    //
    //         //var expToAddS = expToAdd.ToString();
    //         //var expMainS = expMain.ToString();
    //     }
    //
    //     return (expMain);
    // }

    #endregion


    public class ExpressionRetriever
    {
        // private static readonly MethodInfo containsMethod = typeof(string).GetMethod("Contains");

        private static readonly MethodInfo containsMethod =
            typeof(string).GetMethod("Contains", new[] { typeof(string) });
        //private static readonly MethodInfo containsMethod = typeof(Enumerable).GetMethods().First(m => m.Name == "Contains" && m.GetParameters().Length == 2);

        private static readonly MethodInfo startsWithMethod =
            typeof(string).GetMethod("StartsWith", new[] { typeof(string) });

        private static readonly MethodInfo endsWithMethod =
            typeof(string).GetMethod("EndsWith", new[] { typeof(string) });

        public static string GetExpressionString(ExpressionFilter filter)
        {
            switch (filter.Comparison)
            {
                case FilterTypes.Equal:
                    return filter.PropertyName + "=" + filter.Value;
                case FilterTypes.GreaterThan:
                    return filter.PropertyName + " > " + filter.Value;
                case FilterTypes.GreaterThanOrEqual:
                    return filter.PropertyName + " >= " + filter.Value;
                case FilterTypes.LessThan:
                    return filter.PropertyName + " < " + filter.Value;
                case FilterTypes.LessThanOrEqual:
                    return filter.PropertyName + " <= " + filter.Value;
                case FilterTypes.NotEqual:
                    return filter.PropertyName + " <> " + filter.Value;
                case FilterTypes.Contains:
                    return filter.PropertyName + " like %" + filter.Value + " %";
                case FilterTypes.StartsWith:
                    return filter.PropertyName + " like " + filter.Value + " %";
                case FilterTypes.EndsWith:
                    return filter.PropertyName + " like %" + filter.Value;

                default:
                    return null;
            }
        }

        public static Expression GetExpression<T>(ParameterExpression param, ExpressionFilter filter)
        {
            MemberExpression member = null;

            if (filter.PropertyName.Contains("."))
            {
                string[] split = filter.PropertyName.Split(".");

                if (split.Length > 0)
                {
                    var parentProp = Expression.Property(param, split[0]);
                    member = Expression.Property(parentProp, split[1]);
                }
                else
                    throw new Exception("Error In Define Include");
            }
            else
            {
                member = Expression.Property(param, filter.PropertyName);
            }

            var propertyType = ((PropertyInfo)member.Member).PropertyType;
            var converter = TypeDescriptor.GetConverter(propertyType);
            if (!converter.CanConvertFrom(typeof(string)))
                throw new NotSupportedException();
            var propertyValue = converter.ConvertFromString(filter.Value?.ToString());

            var constant = Expression.Constant(propertyValue);
            var valueExpression = Expression.Convert(constant, propertyType);
            switch (filter.Comparison)
            {
                case FilterTypes.Equal:
                    return Expression.Equal(member, valueExpression);
                case FilterTypes.GreaterThan:
                    return Expression.GreaterThan(member, valueExpression);
                case FilterTypes.GreaterThanOrEqual:
                    return Expression.GreaterThanOrEqual(member, valueExpression);
                case FilterTypes.LessThan:
                    return Expression.LessThan(member, valueExpression);
                case FilterTypes.LessThanOrEqual:
                    return Expression.LessThanOrEqual(member, valueExpression);
                case FilterTypes.NotEqual:
                    return Expression.NotEqual(member, valueExpression);
                case FilterTypes.Contains:
                    // return Expression.Call(member, containsMethod, valueExpression);
                    // return Expression.Call(member, member.Type.GetMethod("Contains"), valueExpression);
                    return Expression.Call(member, containsMethod, valueExpression);

                case FilterTypes.StartsWith:
                    return Expression.Call(member, startsWithMethod, valueExpression);
                case FilterTypes.EndsWith:
                    return Expression.Call(member, endsWithMethod, valueExpression);
                default:
                    return null;
            }
        }

        public static string ConstructDynamicFilterSp(List<ExpressionFilter> filters)
        {
            string result = null;
            if (filters.Count == 0)
                return null;


            if (filters.Count == 1)
            {
                result = GetExpressionString(filters[0]);
            }
            else
            {
                result = GetExpressionString(filters[0]);
                for (var i = 1; i < filters.Count; i++)
                    if (filters[i - 1].Operation == QueryOperation.Or)
                        result = result + " or " + GetExpressionString(filters[i]);
                    else
                        result = result + " and " + GetExpressionString(filters[i]);
            }

            return result;
        }

        public static Expression<Func<T, bool>> ConstructDynamicFilterSp<T>(List<ExpressionFilter> filters,
            string paramName)
        {
            // No filters passed in #KickIT
            if (filters.Count == 0)
                return null;

            // Create the parameter for the ObjectType (typically the 'x' in your expression (x => 'x')
            // The "parm" string is used strictly for debugging purposes
            var param = Expression.Parameter(typeof(T), paramName);

            // Store the result of a calculated Expression
            Expression exp = null;

            if (filters.Count == 1)
                exp = GetExpression<T>(param, filters[0]); // Create expression from a single instance
            else if (filters.Count == 2)
                exp = GetExpression<T>(param, filters[0],
                    filters[1]); // Create expression that utilizes AndAlso mentality
            else
                // Loop through filters until we have created an expression for each
                while (filters.Count > 0)
                {
                    // Grab initial filters remaining in our List
                    var f1 = filters[0];
                    var f2 = filters[1];

                    // Check if we have already set our Expression
                    if (exp == null)
                        exp = GetExpression<T>(param, filters[0],
                            filters[1]); // First iteration through our filters
                    else
                        exp = Expression.AndAlso(exp,
                            GetExpression<T>(param, filters[0], filters[1])); // Add to our existing expression

                    filters.Remove(f1);
                    filters.Remove(f2);

                    // Odd number, handle this seperately
                    if (filters.Count == 1)
                    {
                        // Pass in our existing expression and our newly created expression from our last remaining filter
                        exp = Expression.AndAlso(exp, GetExpression<T>(param, filters[0]));

                        // Remove filter to break out of while loop
                        filters.RemoveAt(0);
                    }
                }

            return Expression.Lambda<Func<T, bool>>(exp, param);
        }

        private static BinaryExpression GetExpression<T>(ParameterExpression param, ExpressionFilter filter1,
            ExpressionFilter filter2)
        {
            var result1 = GetExpression<T>(param, filter1);
            var result2 = GetExpression<T>(param, filter2);
            return Expression.AndAlso(result1, result2);
        }
    }
}

public class ExpressionFilter
{
    public string PropertyName { get; set; }
    public object Value { get; set; }
    public QueryOperation Operation { get; set; }
    public FilterTypes Comparison { get; set; }
}