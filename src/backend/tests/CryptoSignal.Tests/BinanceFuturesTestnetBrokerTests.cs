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
    public async Task Sends_reduceOnly_on_closing_orders()
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
        Assert.Contains("reduceOnly=true", query, StringComparison.OrdinalIgnoreCase);
    }
}
