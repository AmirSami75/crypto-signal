using System.Net;
using Xunit;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace CryptoSignal.Tests;

public sealed class BinanceFuturesTestnetKlineSourceTests
{
    private static readonly TimeSpan Interval = TimeSpan.FromMinutes(5);

    private static string Kline(long openMs, long closeMs, decimal close = 100m) =>
        $"[{openMs},\"100\",\"110\",\"90\",\"" + close.ToString(System.Globalization.CultureInfo.InvariantCulture) +
        "\",\"10\",\"" + closeMs + "\",\"1000\",\"5\"]";

    private static BinanceFuturesTestnetKlineSource MakeSource(
        FakeHttpMessageHandler handler, out Mock<IHttpClientFactory> factory)
    {
        factory = new Mock<IHttpClientFactory>();
        factory.Setup(f => f.CreateClient(It.IsAny<string>())).Returns(
            new HttpClient(handler) { BaseAddress = new Uri("https://testnet.binancefuture.com") });
        return new BinanceFuturesTestnetKlineSource(factory.Object, NullLogger<BinanceFuturesTestnetKlineSource>.Instance);
    }

    [Fact]
    public async Task Returns_newest_first_window_excluding_forming_candle()
    {
        var now = DateTimeOffset.UtcNow;
        var t0 = now - TimeSpan.FromMinutes(15);
        var open0 = t0.ToUnixTimeMilliseconds();
        var open1 = (t0 + Interval).ToUnixTimeMilliseconds();
        var open2 = (t0 + 2 * Interval).ToUnixTimeMilliseconds();
        var close0 = (t0 + Interval).ToUnixTimeMilliseconds();
        var close1 = (t0 + 2 * Interval).ToUnixTimeMilliseconds();
        var close2 = (t0 + 3 * Interval).ToUnixTimeMilliseconds();
        var formingClose = (now + Interval).ToUnixTimeMilliseconds();

        // Wire rows are newest-first; the last one (forming) has a future close time.
        var body = "[" + Kline(open2, formingClose) + "," + Kline(open2, close2) + "," +
                   Kline(open1, close1) + "," + Kline(open0, close0) + "]";

        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/klines", HttpStatusCode.OK, body);
        var source = MakeSource(handler, out var factory);

        var window = await source.GetClosedCandlesAsync("BTCUSDT", "5m", 2, CancellationToken.None);

        Assert.Equal(2, window.Count);
        Assert.Equal(open1, window[0].OpenTime.ToUnixTimeMilliseconds());
        Assert.Equal(open2, window[1].OpenTime.ToUnixTimeMilliseconds());
        Assert.DoesNotContain(window, c => c.CloseTime > now);
        factory.Verify(f => f.CreateClient(TradingHttpClients.BinanceFuturesTestnet), Times.AtLeastOnce);
    }

    [Fact]
    public async Task Passes_interval_and_symbol_through_without_remapping()
    {
        var now = DateTimeOffset.UtcNow;
        var t0 = now - TimeSpan.FromMinutes(10);
        var open0 = t0.ToUnixTimeMilliseconds();
        var open1 = (t0 + Interval).ToUnixTimeMilliseconds();
        var close0 = (t0 + Interval).ToUnixTimeMilliseconds();
        var close1 = (t0 + 2 * Interval).ToUnixTimeMilliseconds();
        var body = "[" + Kline(open1, close1) + "," + Kline(open0, close0) + "]";

        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/klines", HttpStatusCode.OK, body);
        var source = MakeSource(handler, out _);

        await source.GetClosedCandlesAsync("btcusdt", "5m", 2, CancellationToken.None);

        var sent = Assert.Single(handler.Requests);
        Assert.Contains("symbol=BTCUSDT", sent.RequestUri!.Query);
        Assert.Contains("interval=5m", sent.RequestUri.Query);
        Assert.StartsWith("/fapi/v1/klines", sent.RequestUri.AbsolutePath);
    }

    [Fact]
    public async Task Faults_on_a_window_with_a_missing_candle_gap()
    {
        var now = DateTimeOffset.UtcNow;
        var t0 = now - TimeSpan.FromMinutes(10);
        // 10-minute hole between the two candles (expected 5m step).
        var open0 = t0.ToUnixTimeMilliseconds();
        var open1 = (t0 + 3 * Interval).ToUnixTimeMilliseconds();
        var close0 = (t0 + Interval).ToUnixTimeMilliseconds();
        var close1 = (t0 + 4 * Interval).ToUnixTimeMilliseconds();
        var body = "[" + Kline(open1, close1) + "," + Kline(open0, close0) + "]";

        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/klines", HttpStatusCode.OK, body);
        var source = MakeSource(handler, out _);

        await Assert.ThrowsAsync<InvalidDataException>(
            () => source.GetClosedCandlesAsync("BTCUSDT", "5m", 2, CancellationToken.None));
    }

    [Fact]
    public async Task Faults_on_venue_error_object()
    {
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/klines", HttpStatusCode.OK, "{\"code\":-1121,\"msg\":\"Invalid symbol\"}");
        var source = MakeSource(handler, out _);

        await Assert.ThrowsAsync<InvalidDataException>(
            () => source.GetClosedCandlesAsync("BTCUSDT", "5m", 2, CancellationToken.None));
    }
}
