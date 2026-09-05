using Xunit;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;

namespace CryptoSignal.Tests;

/// <summary>
/// ATR-multiple brackets on <see cref="TradingBot"/>: the fields exist, they are nullable (a bot
/// configured in percent must not silently become an ATR bot), and the geometry they promise is
/// entry ± multiple × ATR — the native form the barrier model was trained on.
/// </summary>
public sealed class BotAtrBracketsTests
{
    private static TradingBot MakeBot() => new()
    {
        Name = "atr-bot",
        Symbol = "BTCUSDT",
        Interval = "1h",
        Venue = MarketVenue.BinanceFuturesTestnet,
    };

    [Fact]
    public void Atr_bracket_fields_default_to_null()
    {
        var bot = MakeBot();

        Assert.Null(bot.TakeProfitAtrMultiple);
        Assert.Null(bot.StopLossAtrMultiple);
    }

    [Fact]
    public void Atr_bracket_fields_round_trip()
    {
        var bot = new TradingBot
        {
            Name = "atr-bot",
            Symbol = "BTCUSDT",
            Interval = "1h",
            Venue = MarketVenue.BinanceFuturesTestnet,
            TakeProfitAtrMultiple = 2m,
            StopLossAtrMultiple = 1m,
        };

        Assert.Equal(2m, bot.TakeProfitAtrMultiple);
        Assert.Equal(1m, bot.StopLossAtrMultiple);
    }

    [Fact]
    public void Long_take_profit_is_entry_plus_multiple_times_atr()
    {
        Assert.Equal(104m, AtrBrackets.TakeProfitPrice(entryPrice: 100m, atr: 2m, atrMultiple: 2m, isLong: true));
    }

    [Fact]
    public void Long_stop_loss_is_entry_minus_multiple_times_atr()
    {
        Assert.Equal(98m, AtrBrackets.StopLossPrice(entryPrice: 100m, atr: 2m, atrMultiple: 1m, isLong: true));
    }

    [Fact]
    public void Short_side_mirrors_the_geometry()
    {
        Assert.Equal(96m, AtrBrackets.TakeProfitPrice(entryPrice: 100m, atr: 2m, atrMultiple: 2m, isLong: false));
        Assert.Equal(102m, AtrBrackets.StopLossPrice(entryPrice: 100m, atr: 2m, atrMultiple: 1m, isLong: false));
    }

    // ── T0.2: the executor resolves the effective bracket from the engine's levels ──

    private static MlTradeLevels Levels(decimal entry = 100m, decimal atr = 2m) =>
        new(EntryPrice: entry, TakeProfitPrice: entry + 1m, StopLossPrice: entry - 1m,
            Atr: atr, RiskRewardRatio: 1, TakeProfitAtr: 0.5, StopLossAtr: 0.5);

    [Fact]
    public void Resolve_replaces_engine_levels_with_atr_brackets_when_configured()
    {
        var (tp, sl) = AtrBrackets.Resolve(2m, 1m, Levels(), isLong: true);

        Assert.Equal(104m, tp);
        Assert.Equal(98m, sl);
    }

    [Fact]
    public void Resolve_passes_engine_levels_through_when_no_atr_bracket_configured()
    {
        var levels = Levels();
        var (tp, sl) = AtrBrackets.Resolve(null, null, levels, isLong: true);

        Assert.Equal(levels.TakeProfitPrice, tp);
        Assert.Equal(levels.StopLossPrice, sl);
    }

    [Fact]
    public void Resolve_uses_the_short_side_geometry_for_shorts()
    {
        var (tp, sl) = AtrBrackets.Resolve(2m, 1m, Levels(), isLong: false);

        Assert.Equal(96m, tp);
        Assert.Equal(102m, sl);
    }

    [Fact]
    public void Resolve_without_engine_levels_yields_nulls()
    {
        var (tp, sl) = AtrBrackets.Resolve(2m, 1m, null, isLong: true);

        Assert.Null(tp);
        Assert.Null(sl);
    }
}
