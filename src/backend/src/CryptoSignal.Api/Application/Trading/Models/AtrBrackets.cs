using CryptoSignal.Api.Contracts;

namespace CryptoSignal.Api.Application.Trading.Models;

/// <summary>
/// Bracket geometry from ATR multiples — the native form the barrier model consumes. A take-profit
/// "2 ATR away" is the same kind of bet on any market; "2% away" is not.
/// </summary>
public static class AtrBrackets
{
    /// <summary>
    /// The take-profit price implied by an ATR multiple: entry ± multiple × ATR, above for a long,
    /// below for a short. Null when the bot has no ATR bracket configured.
    /// </summary>
    public static decimal? TakeProfitPrice(decimal entryPrice, decimal atr, decimal atrMultiple, bool isLong) =>
        From(entryPrice, atr, atrMultiple, isLong);

    /// <summary>
    /// The stop-loss price implied by an ATR multiple: the mirror of the take-profit geometry.
    /// Null when the bot has no ATR bracket configured.
    /// </summary>
    public static decimal? StopLossPrice(decimal entryPrice, decimal atr, decimal atrMultiple, bool isLong) =>
        From(entryPrice, atr, atrMultiple, !isLong);

    /// <summary>
    /// The effective bracket for a decision: when the bot is configured in ATR multiples, the
    /// engine's percent-derived levels are replaced with entry ± multiple × the engine's own ATR.
    /// Engine levels pass through untouched when no ATR bracket is configured, and nothing is
    /// invented when the engine reported no levels at all (a HOLD).
    /// </summary>
    public static (decimal? TakeProfitPrice, decimal? StopLossPrice) Resolve(
        decimal? takeProfitAtrMultiple,
        decimal? stopLossAtrMultiple,
        MlTradeLevels? engineLevels,
        bool isLong)
    {
        if (engineLevels is null)
            return (null, null);

        var atr = engineLevels.Atr;
        var entry = engineLevels.EntryPrice;

        return (
            takeProfitAtrMultiple is { } tpMultiple
                ? TakeProfitPrice(entry, atr, tpMultiple, isLong)
                : engineLevels.TakeProfitPrice,
            stopLossAtrMultiple is { } slMultiple
                ? StopLossPrice(entry, atr, slMultiple, isLong)
                : engineLevels.StopLossPrice);
    }

    private static decimal? From(decimal entryPrice, decimal atr, decimal atrMultiple, bool above)
    {
        if (atrMultiple <= 0)
            return null;

        var distance = atrMultiple * atr;
        return above ? entryPrice + distance : entryPrice - distance;
    }
}
