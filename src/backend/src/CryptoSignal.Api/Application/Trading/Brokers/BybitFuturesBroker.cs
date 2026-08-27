using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Security;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Brokers;

/// <summary>Bybit v5 USDT-linear demo broker. It never claims PAPER or LIVE.</summary>
/// <remarks>
/// Bybit demo uses the production-shaped v5 API at <c>api-demo.bybit.com</c>, but demo credentials
/// and virtual collateral are isolated from production. The broker still treats every unanswered write
/// as ambiguous and preserves request/response hashes for audit. Leverage is explicit: the broker sends
/// a set-leverage request before each opening order, then includes TP/SL in the order request.
/// </remarks>
public sealed class BybitFuturesBroker(
    IHttpClientFactory httpClientFactory,
    Microsoft.Extensions.Options.IOptions<CryptoSignal.Api.Application.Options.ExchangeOptions> options,
    ILogger<BybitFuturesBroker> logger) : IBroker, IScopedSvcMarker
{
    private readonly IHttpClientFactory _httpClientFactory = httpClientFactory;
    private readonly Microsoft.Extensions.Options.IOptions<CryptoSignal.Api.Application.Options.ExchangeOptions> _options = options;
    private readonly ILogger<BybitFuturesBroker> _logger = logger;

    public string Name => "bybit-futures-demo";

    public bool Supports(OperatingMode mode, MarketVenue venue) =>
        mode == OperatingMode.Sandbox && venue == MarketVenue.Bybit;

    public async Task<BrokerPlacement> PlaceAsync(
        BrokerOrderRequest request,
        VenueCredentials? credentials = null,
        CancellationToken cancellationToken = default)
    {
        if (credentials is not { HasCredentials: true })
            return Rejected("no Bybit demo API credentials are available for this user");
        if (request.Leverage < 1)
            return Rejected("Bybit leverage must be at least 1");
        if (!InstrumentRules.IsOnGrid(request.Quantity, request.Rules.StepSize)
            || request.Quantity < request.Rules.MinQuantity)
            return Rejected("quantity is not on the Bybit instrument grid");
        if (request.Direction == TradeDirection.Long && request.Side != OrderSide.Buy
            || request.Direction == TradeDirection.Short && request.Side != OrderSide.Sell)
            return Rejected("Bybit linear order side does not match its direction");

        // Set leverage is idempotent for the symbol and must succeed before an opening order.
        if (request.Direction is TradeDirection.Long or TradeDirection.Short)
        {
            var leverage = await SendSignedAsync(
                HttpMethod.Post,
                "/v5/position/set-leverage",
                new Dictionary<string, object?>
                {
                    ["category"] = "linear",
                    ["symbol"] = request.Symbol.Trim().ToUpperInvariant(),
                    ["buyLeverage"] = request.Leverage.ToString(CultureInfo.InvariantCulture),
                    ["sellLeverage"] = request.Leverage.ToString(CultureInfo.InvariantCulture),
                },
                credentials,
                request.ClientOrderId + ":leverage",
                cancellationToken);
            if (leverage.Outcome != BrokerOutcome.Accepted)
                return leverage;
        }

        var body = new Dictionary<string, object?>
        {
            ["category"] = "linear",
            ["symbol"] = request.Symbol.Trim().ToUpperInvariant(),
            ["side"] = request.Side == OrderSide.Buy ? "Buy" : "Sell",
            ["orderType"] = request.Type == OrderType.Market ? "Market" : "Limit",
            ["qty"] = request.Quantity.ToString(CultureInfo.InvariantCulture),
            ["positionIdx"] = 0,
            ["orderLinkId"] = request.ClientOrderId,
            ["reduceOnly"] = request.Direction is not (TradeDirection.Long or TradeDirection.Short),
        };
        if (request.Type != OrderType.Market && request.LimitPrice is { } price)
            body["price"] = price.ToString(CultureInfo.InvariantCulture);
        if (request.TakeProfitPrice is { } takeProfit)
        {
            body["takeProfit"] = takeProfit.ToString(CultureInfo.InvariantCulture);
            body["tpOrderType"] = "Market";
            body["tpslMode"] = "Full";
        }
        if (request.StopLossPrice is { } stopLoss)
        {
            body["stopLoss"] = stopLoss.ToString(CultureInfo.InvariantCulture);
            body["slOrderType"] = "Market";
            body["tpslMode"] = "Full";
        }

        return await SendSignedAsync(HttpMethod.Post, "/v5/order/create", body, credentials,
            request.ClientOrderId, cancellationToken);
    }

    public async Task<BrokerPlacement> ReconcileAsync(
        string symbol,
        string clientOrderId,
        VenueCredentials? credentials = null,
        CancellationToken cancellationToken = default)
    {
        if (credentials is not { HasCredentials: true })
            return Rejected("no Bybit demo API credentials are available for reconciliation");
        var query = new Dictionary<string, object?>
        {
            ["category"] = "linear",
            ["symbol"] = symbol.Trim().ToUpperInvariant(),
            ["orderLinkId"] = clientOrderId,
        };
        return await SendSignedAsync(HttpMethod.Get, "/v5/order/realtime", query, credentials,
            clientOrderId, cancellationToken);
    }

    public async Task<decimal?> GetAvailableBalanceAsync(
        string quoteAsset,
        VenueCredentials? credentials = null,
        CancellationToken cancellationToken = default)
    {
        if (credentials is not { HasCredentials: true })
            return null;
        try
        {
            var query = new Dictionary<string, object?> { ["accountType"] = "UNIFIED", ["coin"] = quoteAsset.ToUpperInvariant() };
            var response = await SendRawAsync(HttpMethod.Get, "/v5/account/wallet-balance", query, credentials, cancellationToken);
            if (!response.Ok)
                return null;
            using var document = JsonDocument.Parse(response.Body);
            var list = document.RootElement.GetProperty("result").GetProperty("list");
            if (list.GetArrayLength() == 0)
                return null;
            var coins = list[0].GetProperty("coin");
            foreach (var coin in coins.EnumerateArray())
            {
                if (string.Equals(coin.GetProperty("coin").GetString(), quoteAsset, StringComparison.OrdinalIgnoreCase)
                    && decimal.TryParse(coin.GetProperty("walletBalance").GetString(), NumberStyles.Float,
                        CultureInfo.InvariantCulture, out var balance))
                    return balance;
            }
            return null;
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            _logger.LogWarning(exception, "Bybit demo balance could not be read");
            return null;
        }
    }

    private async Task<BrokerPlacement> SendSignedAsync(
        HttpMethod method,
        string path,
        IReadOnlyDictionary<string, object?> parameters,
        VenueCredentials credentials,
        string clientOrderId,
        CancellationToken cancellationToken)
    {
        var response = await SendRawAsync(method, path, parameters, credentials, cancellationToken);
        if (response.Ambiguous)
            return Ambiguous($"Bybit demo transport was ambiguous for {clientOrderId}; reconcile before retrying", response.RequestHash);
        if (!response.Ok)
            return Rejected($"Bybit demo rejected the request: {DescribeError(response.Body)}", response.RequestHash, response.ResponseHash);

        using var document = JsonDocument.Parse(response.Body);
        var root = document.RootElement;
        if (root.GetProperty("retCode").GetInt32() != 0)
            return Rejected($"Bybit demo refused the request: {root.GetProperty("retMsg").GetString()}", response.RequestHash, response.ResponseHash);
        var result = root.TryGetProperty("result", out var resultElement) ? resultElement : default;
        var orderId = result.ValueKind == JsonValueKind.Object && result.TryGetProperty("orderId", out var id)
            ? id.GetString()
            : null;
        return new BrokerPlacement(BrokerOutcome.Accepted, ExchangeOrderStatus.New, orderId, 0m, null, [],
            response.RequestHash, response.ResponseHash);
    }

    private async Task<RawResponse> SendRawAsync(
        HttpMethod method,
        string path,
        IReadOnlyDictionary<string, object?> parameters,
        VenueCredentials credentials,
        CancellationToken cancellationToken)
    {
        var exchange = _options.Value.For(MarketVenue.Bybit);
        var timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString(CultureInfo.InvariantCulture);
        const string recvWindow = "5000";
        var json = method == HttpMethod.Get ? string.Empty : JsonSerializer.Serialize(parameters);
        var query = method == HttpMethod.Get
            ? string.Join('&', parameters.Select(p => $"{Uri.EscapeDataString(p.Key)}={Uri.EscapeDataString(Value(p.Value))}"))
            : string.Empty;
        var signPayload = timestamp + credentials.ApiKey + recvWindow + (method == HttpMethod.Get ? query : json);
        var signature = Convert.ToHexStringLower(HMACSHA256.HashData(
            Encoding.UTF8.GetBytes(credentials.ApiSecret), Encoding.UTF8.GetBytes(signPayload)));
        var uri = query.Length == 0 ? path : $"{path}?{query}";
        var requestHash = Hash($"{method.Method} {uri}|{json}");
        using var message = new HttpRequestMessage(method, uri);
        message.Headers.Add("X-BAPI-API-KEY", credentials.ApiKey);
        message.Headers.Add("X-BAPI-TIMESTAMP", timestamp);
        message.Headers.Add("X-BAPI-RECV-WINDOW", recvWindow);
        message.Headers.Add("X-BAPI-SIGN", signature);
        if (json.Length > 0)
            message.Content = new StringContent(json, Encoding.UTF8, "application/json");
        try
        {
            var client = _httpClientFactory.CreateClient(TradingHttpClients.ForVenue(MarketVenue.Bybit));
            using var response = await client.SendAsync(message, cancellationToken);
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            return new RawResponse(response.IsSuccessStatusCode, false, body, requestHash, Hash(body));
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return new RawResponse(false, true, string.Empty, requestHash, null);
        }
        catch (HttpRequestException)
        {
            return new RawResponse(false, true, string.Empty, requestHash, null);
        }
    }

    private static string Value(object? value) => value switch
    {
        null => string.Empty,
        IFormattable formattable => formattable.ToString(null, CultureInfo.InvariantCulture),
        _ => value.ToString() ?? string.Empty,
    };

    private static string Hash(string value) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    private static string DescribeError(string body) => body.Length > 400 ? body[..400] : body;
    private static BrokerPlacement Rejected(string detail, string? requestHash = null, string? responseHash = null) =>
        new(BrokerOutcome.Rejected, ExchangeOrderStatus.Rejected, null, 0m, null, [], requestHash, responseHash, detail);
    private static BrokerPlacement Ambiguous(string detail, string? requestHash = null) =>
        new(BrokerOutcome.Ambiguous, ExchangeOrderStatus.Unknown, null, 0m, null, [], requestHash, null, detail);

    private sealed record RawResponse(bool Ok, bool Ambiguous, string Body, string RequestHash, string? ResponseHash);
}
