using System.Net;
using Xunit;
using System.Security.Cryptography;
using System.Text;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Application.Security;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Brokers;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;

namespace CryptoSignal.Tests;

public sealed class BinanceFuturesTestnetBrokerTests
{
    private static readonly VenueCredentials Creds = new("test-api-key", "test-api-secret");

    private static readonly InstrumentRules Rules = new(
        Symbol: "BTCUSDT", BaseAsset: "BTC", QuoteAsset: "USDT",
        TickSize: 0.1m, StepSize: 0.001m, MinQuantity: 0.001m, MaxQuantity: 1000m,
        MinNotional: 10m, IsTradable: true, SupportsMarketOrders: true,
        PriceScale: 1, QuantityScale: 3);

    private static BinanceFuturesTestnetBroker MakeBroker(
        FakeHttpMessageHandler handler, out Mock<IHttpClientFactory> factory)
    {
        factory = new Mock<IHttpClientFactory>();
        factory.Setup(f => f.CreateClient(It.IsAny<string>())).Returns(
            new HttpClient(handler) { BaseAddress = new Uri("https://testnet.binancefuture.com") });
        var options = Options.Create(new ExchangeOptions());
        return new BinanceFuturesTestnetBroker(factory.Object, options, NullLogger<BinanceFuturesTestnetBroker>.Instance);
    }

    private static string IndependentSignature(string query, string secret)
    {
        var hash = HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret), Encoding.UTF8.GetBytes(query));
        return Convert.ToHexStringLower(hash);
    }

    private static string QueryWithoutSignature(string query)
    {
        var parts = query.TrimStart('?').Split('&')
            .Where(p => !p.StartsWith("signature=", StringComparison.Ordinal));
        return string.Join("&", parts);
    }

    [Fact]
    public async Task Signs_order_request_with_hmac_sha256_independent_of_handler()
    {
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("/fapi/v1/order", HttpStatusCode.OK,
            "{\"orderId\":123,\"symbol\":\"BTCUSDT\",\"status\":\"FILLED\"," +
            "\"clientOrderId\":\"oid-1\",\"executedQty\":\"0.01\",\"avgPrice\":\"100.0\"," +
            "\"updateTime\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
        var broker = MakeBroker(handler, out var factory);

        var request = new BrokerOrderRequest(
            "oid-1", "BTCUSDT", MarketVenue.BinanceFuturesTestnet, Rules, TradeDirection.Long,
            OrderSide.Buy, OrderType.Market, 0.01m, 100m, Leverage: 2);

        var placement = await broker.PlaceAsync(request, Creds, CancellationToken.None);

        var orderReq = handler.Requests.First(r => r.RequestUri!.AbsolutePath == "/fapi/v1/order");
        var captured = orderReq.RequestUri!.Query;
        var expected = IndependentSignature(QueryWithoutSignature(captured), Creds.ApiSecret);
        Assert.Contains("signature=" + expected, captured);
        Assert.Equal(Creds.ApiKey, orderReq.Headers.GetValues("X-MBX-APIKEY").Single());
        Assert.Equal(BrokerOutcome.Accepted, placement.Outcome);
        factory.Verify(f => f.CreateClient(TradingHttpClients.BinanceFuturesTestnet), Times.AtLeastOnce);
    }

    [Fact]
    public async Task Synthesises_the_fill_from_cumQuote_when_avgPrice_is_still_zero()
    {
        // Observed live on 2026-11-21 (FETUSDT): the RESULT response can report executedQty > 0 with
        // avgPrice "0.0000000" while cumQuote is already priced. Without the derivation no fill is
        // built, the position row is never written, and the bot trades on believing it is flat.
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("/fapi/v1/order", HttpStatusCode.OK,
            "{\"orderId\":359082947,\"symbol\":\"FETUSDT\",\"status\":\"FILLED\"," +
            "\"clientOrderId\":\"oid-zero-avg\",\"executedQty\":\"93\",\"avgPrice\":\"0.0000000\"," +
            "\"cumQuote\":\"9.9975000\",\"updateTime\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
        var broker = MakeBroker(handler, out _);

        var request = new BrokerOrderRequest(
            "oid-zero-avg", "FETUSDT", MarketVenue.BinanceFuturesTestnet, Rules, TradeDirection.Short,
            OrderSide.Sell, OrderType.Market, 93m, 0.1075m, Leverage: 1);

        var placement = await broker.PlaceAsync(request, Creds, CancellationToken.None);

        var fill = Assert.Single(placement.Fills);
        Assert.Equal(93m, fill.Quantity);
        Assert.Equal(9.9975m / 93m, fill.Price);
    }

    [Fact]
    public async Task Follows_up_the_order_when_the_RESULT_carries_no_price_at_all()
    {
        // Live shape on 2026-11-21: POST /fapi/v1/order answered FILLED with executedQty 93 but
        // avgPrice AND cumQuote both "0.0000000". The follow-up GET carries the real price; without it
        // no fill row exists and the position (or its close) is never recorded.
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("POST", "/fapi/v1/order", HttpStatusCode.OK,
            "{\"orderId\":359085336,\"symbol\":\"FETUSDT\",\"status\":\"FILLED\"," +
            "\"clientOrderId\":\"oid-priceless\",\"executedQty\":\"93\",\"avgPrice\":\"0.0000000\"," +
            "\"cumQuote\":\"0.0000000\",\"updateTime\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
        handler.Respond("GET", "/fapi/v1/order", HttpStatusCode.OK,
            "{\"orderId\":359085336,\"symbol\":\"FETUSDT\",\"status\":\"FILLED\"," +
            "\"clientOrderId\":\"oid-priceless\",\"executedQty\":\"93\",\"avgPrice\":\"0.1074000\"," +
            "\"cumQuote\":\"9.9882000\",\"updateTime\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
        var broker = MakeBroker(handler, out _);

        var request = new BrokerOrderRequest(
            "oid-priceless", "FETUSDT", MarketVenue.BinanceFuturesTestnet, Rules, TradeDirection.Short,
            OrderSide.Buy, OrderType.Market, 93m, 0.1074m, Leverage: 1);

        var placement = await broker.PlaceAsync(request, Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Accepted, placement.Outcome);
        var fill = Assert.Single(placement.Fills);
        Assert.Equal(93m, fill.Quantity);
        Assert.Equal(0.1074m, fill.Price);
        Assert.Contains(handler.Requests,
            r => r.Method == HttpMethod.Get && r.RequestUri!.AbsolutePath == "/fapi/v1/order");
    }

    [Fact]
    public async Task Rejects_when_no_credentials_configured()
    {
        var handler = new FakeHttpMessageHandler();
        var broker = MakeBroker(handler, out _);

        var request = new BrokerOrderRequest(
            "oid-2", "BTCUSDT", MarketVenue.BinanceFuturesTestnet, Rules, TradeDirection.Long,
            OrderSide.Buy, OrderType.Market, 0.01m, 100m, Leverage: 2);

        var placement = await broker.PlaceAsync(request, null, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Rejected, placement.Outcome);
        Assert.False(handler.Requests.Any());
    }

    [Fact]
    public async Task Rejects_on_venue_business_error()
    {
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("/fapi/v1/order", HttpStatusCode.BadRequest,
            "{\"code\":-2019,\"msg\":\"Margin is insufficient\"}");
        var broker = MakeBroker(handler, out _);

        var request = new BrokerOrderRequest(
            "oid-3", "BTCUSDT", MarketVenue.BinanceFuturesTestnet, Rules, TradeDirection.Short,
            OrderSide.Sell, OrderType.Market, 0.01m, 100m, Leverage: 2);

        var placement = await broker.PlaceAsync(request, Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Rejected, placement.Outcome);
        Assert.Contains("Margin is insufficient", placement.Detail ?? string.Empty);
    }

    [Fact]
    public void Supports_only_sandbox_with_the_futures_testnet_venue()
    {
        var broker = MakeBroker(new FakeHttpMessageHandler(), out _);
        Assert.True(broker.Supports(OperatingMode.Sandbox, MarketVenue.BinanceFuturesTestnet));
        Assert.False(broker.Supports(OperatingMode.Live, MarketVenue.BinanceFuturesTestnet));
        Assert.False(broker.Supports(OperatingMode.Paper, MarketVenue.BinanceFuturesTestnet));
        Assert.False(broker.Supports(OperatingMode.Sandbox, MarketVenue.BinanceMainnet));
    }

    [Fact]
    public async Task Omits_reduceOnly_on_entry_orders()
    {
        // Binance error -1106: `reduceOnly` sent when not required. Entries must omit it entirely.
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("/fapi/v1/order", HttpStatusCode.OK,
            "{\"orderId\":124,\"symbol\":\"BTCUSDT\",\"status\":\"FILLED\"," +
            "\"clientOrderId\":\"oid-entry\",\"executedQty\":\"0.01\",\"avgPrice\":\"100.0\"," +
            "\"updateTime\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
        var broker = MakeBroker(handler, out _);

        var request = new BrokerOrderRequest(
            "oid-entry", "BTCUSDT", MarketVenue.BinanceFuturesTestnet, Rules, TradeDirection.Long,
            OrderSide.Buy, OrderType.Market, 0.01m, 100m, Leverage: 2);

        var placement = await broker.PlaceAsync(request, Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Accepted, placement.Outcome);
        var query = handler.Requests.First(r => r.RequestUri!.AbsolutePath == "/fapi/v1/order").RequestUri!.Query;
        Assert.DoesNotContain("reduceOnly", query, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Accepts_the_executors_close_shape_and_never_sends_reduceOnly()
    {
        // What BotTickExecutor actually sends for a stop-loss exit on a short: the position direction is
        // carried and the side is the opposite one. The adapter must treat that as a close (hedge mode),
        // not reject it — this shipped as a live bug on 2026-11-21 (FETUSDT exit refused by the guard).
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("/fapi/v1/order", HttpStatusCode.OK,
            "{\"orderId\":126,\"symbol\":\"FETUSDT\",\"status\":\"FILLED\"," +
            "\"clientOrderId\":\"oid-exit\",\"executedQty\":\"93\",\"avgPrice\":\"0.1081\"," +
            "\"updateTime\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
        var broker = MakeBroker(handler, out _);

        var request = new BrokerOrderRequest(
            "oid-exit", "FETUSDT", MarketVenue.BinanceFuturesTestnet, Rules, TradeDirection.Short,
            OrderSide.Buy, OrderType.Market, 93m, 0.1081m, Leverage: 1);

        var placement = await broker.PlaceAsync(request, Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Accepted, placement.Outcome);
        var query = handler.Requests.First(r => r.RequestUri!.AbsolutePath == "/fapi/v1/order").RequestUri!.Query;
        Assert.Contains("positionSide=SHORT", query, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("side=BUY", query, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("reduceOnly", query, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Omits_reduceOnly_on_flat_orders_too()
    {
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/order", HttpStatusCode.OK,
            "{\"orderId\":125,\"symbol\":\"BTCUSDT\",\"status\":\"FILLED\"," +
            "\"clientOrderId\":\"oid-close\",\"executedQty\":\"0.01\",\"avgPrice\":\"100.0\"," +
            "\"updateTime\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
        var broker = MakeBroker(handler, out _);

        var request = new BrokerOrderRequest(
            "oid-close", "BTCUSDT", MarketVenue.BinanceFuturesTestnet, Rules, TradeDirection.Flat,
            OrderSide.Sell, OrderType.Market, 0.01m, 100m, Leverage: 2);

        var placement = await broker.PlaceAsync(request, Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Accepted, placement.Outcome);
        var query = handler.Requests.First(r => r.RequestUri!.AbsolutePath == "/fapi/v1/order").RequestUri!.Query;
        Assert.DoesNotContain("reduceOnly", query, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("positionSide=BOTH", query, StringComparison.OrdinalIgnoreCase);
    }
}
