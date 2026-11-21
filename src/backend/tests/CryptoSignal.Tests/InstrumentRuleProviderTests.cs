using System.Net;
using System.Text;
using Xunit;
using CryptoSignal.Api.Application.Trading.Instruments;
using CryptoSignal.Api.Domain.Enums.Trading;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace CryptoSignal.Tests;

/// <summary>
/// The venue's grid decides the fill price and the size of every order, so a provider that silently
/// resolves the wrong market is worse than one that fails: the platform trades a grid it never asked for.
/// </summary>
public sealed class InstrumentRuleProviderTests
{
    private const string BtcEntry = """
        {"symbol":"BTCUSDT","status":"TRADING","baseAsset":"BTC","quoteAsset":"USDT",
         "orderTypes":["LIMIT","MARKET"],"isSpotTradingAllowed":true,
         "filters":[{"filterType":"PRICE_FILTER","tickSize":"0.10"},
                    {"filterType":"LOT_SIZE","stepSize":"0.001","minQty":"0.001","maxQty":"1000"},
                    {"filterType":"MARKET_LOT_SIZE","stepSize":"0.001","minQty":"0.001","maxQty":"120"}]}
        """;

    private const string McaEntry = """
        {"symbol":"MOCAUSDT","status":"TRADING","baseAsset":"MOCA","quoteAsset":"USDT",
         "orderTypes":["LIMIT","MARKET"],"isSpotTradingAllowed":true,
         "filters":[{"filterType":"PRICE_FILTER","tickSize":"0.0000100"},
                    {"filterType":"LOT_SIZE","stepSize":"1","minQty":"1","maxQty":"3000000"},
                    {"filterType":"MARKET_LOT_SIZE","stepSize":"1","minQty":"1","maxQty":"300000"}]}
        """;

    /// <summary>Answers the symbol-filtered call with the venue's flagship pair, the way Binance's futures
    /// testnet does, and the unfiltered call with the whole listing.</summary>
    private sealed class FilterIgnoringHandler : HttpMessageHandler
    {
        public int Calls { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Calls++;
            var query = request.RequestUri!.Query;
            var body = query.Contains("symbol=", StringComparison.OrdinalIgnoreCase)
                ? "{\"symbols\":[" + BtcEntry + "]}"
                : "{\"symbols\":[" + BtcEntry + "," + McaEntry + "]}";
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json"),
            });
        }
    }

    private static InstrumentRuleProvider MakeProvider(HttpMessageHandler handler)
    {
        var factory = new Mock<IHttpClientFactory>();
        factory.Setup(f => f.CreateClient(It.IsAny<string>())).Returns(
            new HttpClient(handler) { BaseAddress = new Uri("https://testnet.binancefuture.com") });
        return new InstrumentRuleProvider(factory.Object, NullLogger<InstrumentRuleProvider>.Instance);
    }

    [Fact]
    public async Task Resolves_the_requested_symbol_when_the_venue_ignores_the_symbol_filter()
    {
        var handler = new FilterIgnoringHandler();
        var provider = MakeProvider(handler);

        var rules = await provider.GetRulesAsync(
            MarketVenue.BinanceFuturesTestnet, "MOCAUSDT", CancellationToken.None);

        // The bug this test exists for: the filtered call answered BTCUSDT, and without the fallback the
        // order would have been priced on a 0.10 tick and capped at BTC's 120-unit market lot.
        Assert.Equal("MOCAUSDT", rules.Symbol);
        Assert.Equal(0.00001m, rules.TickSize);
        Assert.Equal(300000m, rules.MaxQuantity);
        Assert.True(rules.SupportsMarketOrders);
    }

    [Fact]
    public async Task A_matching_symbol_filter_costs_one_call()
    {
        var handler = new FilterIgnoringHandler();
        var provider = MakeProvider(handler);

        await provider.GetRulesAsync(MarketVenue.BinanceFuturesTestnet, "BTCUSDT", CancellationToken.None);

        Assert.Equal(1, handler.Calls);
    }

    [Fact]
    public async Task An_unlisted_symbol_throws_instead_of_borrowing_another_market()
    {
        var provider = MakeProvider(new FilterIgnoringHandler());

        var exception = await Assert.ThrowsAsync<InstrumentRulesUnavailableException>(() =>
            provider.GetRulesAsync(MarketVenue.BinanceFuturesTestnet, "NOPEUSDT", CancellationToken.None));

        Assert.Contains("NOPEUSDT", exception.Message, StringComparison.Ordinal);
    }
}
