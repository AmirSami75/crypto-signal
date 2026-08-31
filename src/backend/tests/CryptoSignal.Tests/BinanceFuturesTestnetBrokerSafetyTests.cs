using System.Net;
using System.Text.RegularExpressions;
using Xunit;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Application.Security;
using CryptoSignal.Api.Application.Trading.Brokers;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;

namespace CryptoSignal.Tests;

/// <summary>
/// Phase 5.4 failure-injection tests for the Binance Futures testnet broker: proves the adapter fails
/// closed and never blind-retries when the venue misbehaves or is misconfigured.
/// </summary>
public sealed class BinanceFuturesTestnetBrokerSafetyTests
{
    private static readonly VenueCredentials Creds = new("test-api-key", "test-api-secret");

    private static readonly InstrumentRules Rules = new(
        Symbol: "BTCUSDT", BaseAsset: "BTC", QuoteAsset: "USDT",
        TickSize: 0.1m, StepSize: 0.001m, MinQuantity: 0.001m, MaxQuantity: 1000m,
        MinNotional: 10m, IsTradable: true, SupportsMarketOrders: true,
        PriceScale: 1, QuantityScale: 3);

    private static BinanceFuturesTestnetBroker MakeBroker(FakeHttpMessageHandler handler)
    {
        var factory = new Mock<IHttpClientFactory>();
        factory.Setup(f => f.CreateClient(It.IsAny<string>())).Returns(
            new HttpClient(handler) { BaseAddress = new Uri("https://testnet.binancefuture.com") });
        return new BinanceFuturesTestnetBroker(
            factory.Object, Options.Create(new ExchangeOptions()), NullLogger<BinanceFuturesTestnetBroker>.Instance);
    }

    private static BrokerOrderRequest Opening(OrderSide side, TradeDirection dir, decimal qty = 0.01m, int leverage = 2) =>
        new("oid-x", "BTCUSDT", MarketVenue.BinanceFuturesTestnet, Rules, dir, side, OrderType.Market, qty, 100m, Leverage: leverage);

    [Fact]
    public void Bitunix_sandbox_resolves_to_no_broker()
    {
        var broker = MakeBroker(new FakeHttpMessageHandler());
        // Acceptance 5.4: Bitunix must never map Sandbox to a live-capable broker.
        Assert.False(broker.Supports(OperatingMode.Sandbox, MarketVenue.Bitunix));
        Assert.False(broker.Supports(OperatingMode.Live, MarketVenue.BinanceFuturesTestnet));
    }

    [Fact]
    public async Task Rejects_when_leverage_is_below_one()
    {
        var handler = new FakeHttpMessageHandler();
        var broker = MakeBroker(handler);

        var placement = await broker.PlaceAsync(Opening(OrderSide.Buy, TradeDirection.Long, leverage: 0), Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Rejected, placement.Outcome);
        Assert.False(handler.Requests.Any()); // nothing left the process
    }

    [Fact]
    public async Task Rejects_when_quantity_is_off_the_instrument_grid()
    {
        var handler = new FakeHttpMessageHandler();
        var broker = MakeBroker(handler);

        var placement = await broker.PlaceAsync(Opening(OrderSide.Buy, TradeDirection.Long, qty: 0.0001m), Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Rejected, placement.Outcome);
        Assert.DoesNotContain(handler.Requests, r => r.RequestUri!.AbsolutePath == "/fapi/v1/order");
    }

    [Fact]
    public async Task Returns_ambiguous_on_venue_5xx()
    {
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("/fapi/v1/order", HttpStatusCode.InternalServerError,
            "{\"code\":-1000,\"msg\":\"server error\"}");
        var broker = MakeBroker(handler);

        var placement = await broker.PlaceAsync(Opening(OrderSide.Buy, TradeDirection.Long), Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Ambiguous, placement.Outcome); // must reconcile, never blind-retry
    }

    [Fact]
    public async Task Returns_rejected_on_venue_4xx()
    {
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("/fapi/v1/order", HttpStatusCode.NotFound, "{\"code\":-1,\"msg\":\"unknown\"}");
        var broker = MakeBroker(handler);

        var placement = await broker.PlaceAsync(Opening(OrderSide.Buy, TradeDirection.Long), Creds, CancellationToken.None);

        Assert.Equal(BrokerOutcome.Rejected, placement.Outcome);
    }

    [Fact]
    public async Task Transport_timeout_faults_without_placing_an_order()
    {
        var handler = new FakeHttpMessageHandler();
        handler.Throw(new TaskCanceledException("simulated timeout"));
        var broker = MakeBroker(handler);

        var placement = await broker.PlaceAsync(Opening(OrderSide.Buy, TradeDirection.Long), Creds, CancellationToken.None);

        // Safety: a timeout must not be read as a fill. The adapter must stop and force reconciliation.
        Assert.NotEqual(BrokerOutcome.Accepted, placement.Outcome);
        Assert.DoesNotContain(handler.Requests, r => r.RequestUri!.AbsolutePath == "/fapi/v1/order");
    }

    [Fact]
    public async Task Duplicate_client_order_id_is_idempotent()
    {
        var handler = new FakeHttpMessageHandler();
        handler.Respond("/fapi/v1/leverage", HttpStatusCode.OK, "{}");
        handler.Respond("/fapi/v1/order", HttpStatusCode.OK,
            "{\"orderId\":1,\"symbol\":\"BTCUSDT\",\"status\":\"FILLED\",\"clientOrderId\":\"oid-x\"," +
            "\"executedQty\":\"0.01\",\"avgPrice\":\"100.0\",\"updateTime\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
        var broker = MakeBroker(handler);

        await broker.PlaceAsync(Opening(OrderSide.Buy, TradeDirection.Long), Creds, CancellationToken.None);
        await broker.PlaceAsync(Opening(OrderSide.Buy, TradeDirection.Long), Creds, CancellationToken.None);

        var ids = handler.Requests
            .Where(r => r.RequestUri!.AbsolutePath == "/fapi/v1/order")
            .Select(r => Regex.Match(r.RequestUri!.Query, "newClientOrderId=([^&]+)").Groups[1].Value)
            .ToList();

        Assert.Equal(2, ids.Count);
        Assert.Equal(ids[0], ids[1]); // same client id => same orderLinkId, no second position
    }
}
