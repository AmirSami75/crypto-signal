using System.Net;
using Xunit;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Domain.Enums.Trading;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace CryptoSignal.Tests;

/// <summary>
/// T0.3 — multi-timeframe kline access. <see cref="IMarketDataSource.GetClosedCandlesAsync"/> takes the
/// interval as a parameter, so the same source must serve different intervals back to back (the shape
/// the multi-timeframe confluence work needs) and must pass the requested interval through to the venue
/// unmodified — a silently rewritten interval would mislabel every candle in the window.
/// </summary>
public sealed class MultiIntervalKlineTests
{
    private static BinanceFuturesTestnetKlineSource MakeSource(
        FakeHttpMessageHandler handler)
    {
        var factory = new Mock<IHttpClientFactory>();
        factory.Setup(f => f.CreateClient(It.IsAny<string>())).Returns(
            new HttpClient(handler) { BaseAddress = new Uri("https://testnet.binancefuture.com") });
        return new BinanceFuturesTestnetKlineSource(
            factory.Object, NullLogger<BinanceFuturesTestnetKlineSource>.Instance);
    }

    private static string Kline(long openMs, long closeMs) =>
        $"[{openMs},\"100\",\"110\",\"90\",\"100\",\"10\",{closeMs},\"1000\",\"5\"]";

    [Fact]
    public async Task Same_source_serves_two_intervals_back_to_back()
    {
        var now = DateTimeOffset.UtcNow;
        var hour = TimeSpan.FromHours(1);
        var minute = TimeSpan.FromMinutes(5);

        var h0 = now - TimeSpan.FromHours(2);
        var h1 = h0 + hour;
        var m0 = now - TimeSpan.FromMinutes(10);
        var m1 = m0 + minute;

        var hourlyHandler = new FakeHttpMessageHandler();
        hourlyHandler.Respond("/fapi/v1/klines", HttpStatusCode.OK,
            "[" + Kline(h1.ToUnixTimeMilliseconds(), (h1 + hour).ToUnixTimeMilliseconds()) + "," +
            Kline(h0.ToUnixTimeMilliseconds(), (h0 + hour).ToUnixTimeMilliseconds()) + "]");
        var hourlySource = MakeSource(hourlyHandler);
        var hourly = await hourlySource.GetClosedCandlesAsync("BTCUSDT", "1h", 2, CancellationToken.None);

        var fiveminHandler = new FakeHttpMessageHandler();
        fiveminHandler.Respond("/fapi/v1/klines", HttpStatusCode.OK,
            "[" + Kline(m1.ToUnixTimeMilliseconds(), (m1 + minute).ToUnixTimeMilliseconds()) + "," +
            Kline(m0.ToUnixTimeMilliseconds(), (m0 + minute).ToUnixTimeMilliseconds()) + "]");
        var fiveminSource = MakeSource(fiveminHandler);
        var fivemin = await fiveminSource.GetClosedCandlesAsync("BTCUSDT", "5m", 2, CancellationToken.None);

        Assert.Equal(2, hourly.Count);
        Assert.Equal(2, fivemin.Count);
        Assert.Equal(hour, hourly[1].OpenTime - hourly[0].OpenTime);
        Assert.Equal(minute, fivemin[1].OpenTime - fivemin[0].OpenTime);
    }

    [Fact]
    public async Task Requested_interval_is_sent_to_the_venue_verbatim()
    {
        var now = DateTimeOffset.UtcNow;
        var fourHours = TimeSpan.FromHours(4);
        var t0 = now - TimeSpan.FromHours(8);
        var body = "[" + Kline((t0 + fourHours).ToUnixTimeMilliseconds(),
                        (t0 + 2 * fourHours).ToUnixTimeMilliseconds()) + "," +
                   Kline(t0.ToUnixTimeMilliseconds(), (t0 + fourHours).ToUnixTimeMilliseconds()) + "]";

        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/klines", HttpStatusCode.OK, body);
        var source = MakeSource(handler);

        await source.GetClosedCandlesAsync("BTCUSDT", "4h", 2, CancellationToken.None);

        var sent = Assert.Single(handler.Requests);
        Assert.Contains("interval=4h", sent.RequestUri!.Query);
        Assert.Contains("symbol=BTCUSDT", sent.RequestUri.Query);
    }
}
