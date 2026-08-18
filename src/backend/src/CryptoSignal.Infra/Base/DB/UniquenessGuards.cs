using System.Linq.Expressions;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Exceptions.Common;

namespace CryptoSignal.Infra.Base.DB;

public static class UniquenessGuards
{
    // ---------- Public API ----------

    /// <summary>
    /// Throws LogicException if any row matches 'predicate'.
    /// Use for CREATE scenarios.
    /// </summary>
    public static async Task EnsureNotExistsAsync<T>(
        IQueryable<T> source,
        Expression<Func<T, bool>> predicate,
        string userMessage,
        CancellationToken ct = default)
    {
        if (await source.AnyAsync(predicate, ct))
            throw new LogicException(userMessage);
    }

    /// <summary>
    /// Throws LogicException if any row (excluding 'id' via keySelector) matches 'predicateWithoutId'.
    /// Use for UPDATE scenarios.
    /// </summary>
    public static async Task EnsureNotExistsAsync<T, TKey>(
        IQueryable<T> source,
        Expression<Func<T, bool>> predicateWithoutId,
        Expression<Func<T, TKey>> keySelector,
        TKey id,
        string userMessage,
        CancellationToken ct = default)
        where TKey : notnull
    {
        // Build: e => predicateWithoutId(e) && keySelector(e) != id
        var p = Expression.Parameter(typeof(T), "e");

        var left = Rebind(predicateWithoutId, p).Body; // predicateWithoutId with 'e'
        var keyBody = Rebind(keySelector, p).Body; // keySelector with 'e'
        var idConst = ToTypedConstant(id, keyBody.Type); // constant typed to selector body
        var notSameEntity = Expression.NotEqual(keyBody, idConst);

        var body = Expression.AndAlso(left, notSameEntity);
        var combined = Expression.Lambda<Func<T, bool>>(body, p);

        if (await source.AnyAsync(combined, ct))
            throw new LogicException(userMessage);
    }

    /// <summary>
    /// Single-field uniqueness with optional normalizer (e.g., Trim/ToUpper).
    /// Include 'baseFilter' (e.g., x => !x.IsDeleted) to mimic filtered unique indexes.
    /// </summary>
    public static Task EnsureUniqueAsync<T, TValue>(
        IQueryable<T> source,
        TValue? value,
        Expression<Func<T, TValue?>> selector,
        string userMessage,
        string? errorCode = null,
        Expression<Func<T, bool>>? baseFilter = null,
        Func<TValue?, TValue?>? normalizer = null,
        CancellationToken ct = default)
    {
        var v = normalizer != null ? normalizer(value) : value;

        var p = Expression.Parameter(typeof(T), "e");
        var selBody = Rebind(selector, p).Body;

        // Build equality with properly typed constant
        var valueConst = ToTypedConstant(v, selBody.Type);
        Expression body = Expression.Equal(selBody, valueConst);

        if (baseFilter != null)
        {
            var baseBody = Rebind(baseFilter, p).Body;
            body = Expression.AndAlso(baseBody, body);
        }

        var pred = Expression.Lambda<Func<T, bool>>(body, p);
        return EnsureNotExistsAsync(source, pred, userMessage, ct);
    }

    /// <summary>
    /// Batch multiple checks in one go. Throws on the first failing check.
    /// </summary>
    public static async Task EnsureAllAsync<T>(
        IQueryable<T> source,
        IEnumerable<UniqueCheck<T>> checks,
        CancellationToken ct = default)
    {
        foreach (var c in checks)
        {
            if (await source.AnyAsync(c.Predicate, ct))
                throw new LogicException(c.UserMessage);
        }
    }

    public readonly record struct UniqueCheck<T>(
        Expression<Func<T, bool>> Predicate,
        string UserMessage);

    // ---------- Private helpers ----------

    private sealed class ReplaceParameterVisitor : ExpressionVisitor
    {
        private readonly ParameterExpression _from;
        private readonly ParameterExpression _to;

        public ReplaceParameterVisitor(ParameterExpression from, ParameterExpression to)
            => (_from, _to) = (from, to);

        protected override Expression VisitParameter(ParameterExpression node)
            => node == _from ? _to : base.VisitParameter(node);
    }

    private static Expression<Func<T, TOut>> Rebind<T, TOut>(
        Expression<Func<T, TOut>> expr, ParameterExpression newParam)
    {
        var visitor = new ReplaceParameterVisitor(expr.Parameters[0], newParam);
        return Expression.Lambda<Func<T, TOut>>(visitor.Visit(expr.Body)!, newParam);
    }

    private static Expression ToTypedConstant(object? value, Type targetType)
    {
        // If null: make 'default(targetType)'
        if (value is null)
            return Expression.Constant(null, targetType);

        var constExpr = Expression.Constant(value);
        // If already assignable, return as-is but with the target type to be safe
        if (targetType.IsAssignableFrom(constExpr.Type))
            return Expression.Constant(value, targetType);

        // Handle nullable target types by converting the constant to the underlying type first
        var underlying = Nullable.GetUnderlyingType(targetType);
        if (underlying != null && underlying.IsAssignableFrom(constExpr.Type))
            return Expression.Convert(Expression.Constant(value, constExpr.Type), targetType);

        // Final fallback: convert constant to target type
        return Expression.Convert(Expression.Constant(value, constExpr.Type), targetType);
    }
}