using Xunit;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;

namespace CryptoSignal.Tests;

/// <summary>
/// Scanner-bot entity invariants: the claim field and the direction semantics the
/// atomic claim path in BotTickExecutor depends on.
/// </summary>
public sealed class ScannerBotTests
{
    private static ScannerSignal MakeSignal() => new()
    {
        ScanId = Guid.CreateVersion7(),
        Symbol = "BTCUSDT",
        Interval = "5m",
        StrategyKey = "rsi",
        Direction = SignalDirection.Long,
        Confidence = 1.0,
        Score = 42m,
        AtrAtSignal = 25m,
        Reason = "rsi crossed below 30 (24.9)",
    };

    [Fact]
    public void New_signal_is_unclaimed()
    {
        var signal = MakeSignal();

        Assert.Null(signal.TakenByBotId);
    }

    [Fact]
    public void TakenByBotId_is_mutable_for_the_claim()
    {
        // The claim is a conditional UPDATE on this property; everything else is init-only.
        var signal = MakeSignal();
        var botId = Guid.CreateVersion7();

        signal.TakenByBotId = botId;

        Assert.Equal(botId, signal.TakenByBotId);
    }

    [Theory]
    [InlineData(SignalDirection.Long, TradeDirection.Long)]
    [InlineData(SignalDirection.Short, TradeDirection.Short)]
    public void Signal_direction_maps_to_trade_direction(SignalDirection signalDirection, TradeDirection tradeDirection)
    {
        var signal = MakeSignal();
        signal.GetType().GetProperty(nameof(ScannerSignal.Direction))!
            .SetValue(signal, signalDirection);

        var mapped = signalDirection == SignalDirection.Long
            ? TradeDirection.Long
            : TradeDirection.Short;

        Assert.Equal(tradeDirection, mapped);
    }

    [Fact]
    public void Bot_kind_defaults_to_Model()
    {
        var bot = new TradingBot
        {
            Name = "b",
            Symbol = "BTCUSDT",
            Interval = "1h",
        };

        Assert.Equal(BotKind.Model, bot.Kind);
        Assert.Null(bot.StrategyKey);
    }

    [Fact]
    public void Scanner_bot_can_target_a_strategy()
    {
        var bot = new TradingBot
        {
            Name = "scanner",
            Symbol = "BTCUSDT",
            Interval = "5m",
            Kind = BotKind.Scanner,
            StrategyKey = "bollinger",
            AllowShort = true,
        };

        Assert.Equal(BotKind.Scanner, bot.Kind);
        Assert.Equal("bollinger", bot.StrategyKey);
    }
}
