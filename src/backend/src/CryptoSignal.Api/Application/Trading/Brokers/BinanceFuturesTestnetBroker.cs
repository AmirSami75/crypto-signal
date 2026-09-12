using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Options;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Security;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Brokers;

/// <summary>
/// USDT-margined futures broker for the Binance Futures testnet (<c>testnet.binancefuture.com</c>).
/// </summary>
/// <remarks>
/// <para>
/// Unlike <see cref="BinanceSpotBroker"/>, this adapter can open SHORT positions — a futures contract
/// is borrowed from the venue, not from the account's existing balance. It therefore honours both
/// <see cref="TradeDirection.Short"/> and <see cref="OrderSide.Sell"/> without arithmetic refusal.
/// The short gate lives upstream in the risk engine and in the operating-mode config, never
/// in the adapter: the adapter does what it is told.
/// </para>
/// <para>
/// <b>Leverage is explicit.</b> Before an opening order, the broker sends a set-leverage request
/// for the symbol. That call is idempotent (the venue dedupes on symbol) and is what makes the
/// bot's <c>Leverage</c> setting is auditable at the venue rather than just in the risk
/// snapshot. The leverage request and the order request carry separate client order ids suffixed
/// <c>:leverage</c>, so they never collide in the audit trail.
/// </para>
/// <para>
/// Futures balance reads return the USDT wallet balance from <c>/fapi/v2/balance</c>, not the
/// spot <c>/api/v3/account</c>. An empty or missing USDT entry resolves to zero (a known empty
/// account), which surfaces as a risk denial rather than a venue fault.
/// </para>
/// <para>
/// The order response shape differs from spot: futures returns <c>avgPrice</c>, <c>executedQty</c>,
/// <c>closePosition</c> and a position-side field set rather than the spot fill array. The broker
/// maps these into the same <see cref="BrokerPlacement"/> envelope.
/// </para>
/// </remarks>
public sealed class BinanceFuturesTestnetBroker(
    IHttpClientFactory httpClientFactory,
    IOptions<ExchangeOptions> options,
    ILogger<BinanceFuturesTestnetBroker> logger)
    : IBroker, IScopedSvcMarker
{
    private readonly IHttpClientFactory _http = httpClientFactory;
    private readonly ExchangeOptions _options = options.Value;
    private readonly ILogger<BinanceFuturesTestnetBroker> _logger = logger;

    /// <inheritdoc/>
    public string Name => "binance-futures-testnet";

    /// <inheritdoc/>
    public MarketVenue Venue => MarketVenue.BinanceFuturesTestnet;

    /// <inheritdoc/>
    public bool Supports(OperatingMode mode, MarketVenue venue) =>
        mode == OperatingMode.Sandbox && venue == Venue;

    /// <inheritdoc/>
    public async Task<BrokerPlacement> PlaceAsync(
        BrokerOrderRequest request,
        VenueCredentials? credentials = null,
        CancellationToken cancellationToken = default)
    {
        var venueCreds = ResolveCredentials(credentials);
        if (venueCreds is not { HasCredentials: true })
            return Rejected(
                $"no API credentials are configured for {Venue}; set Exchange__{Venue}__ApiKey and " +
                $"Exchange__{Venue}__ApiSecret in the server environment");

        if (request.Leverage < 1)
            return Rejected("futures leverage must be at least 1x (use the bot's leverage setting)");

        if (!InstrumentRules.IsOnGrid(request.Quantity, request.Rules.StepSize)
            || request.Quantity < request.Rules.MinQuantity)
            return Rejected("quantity is not on the futures instrument grid");

        // Opening orders carry a position direction; closing orders must match the open one.
        if (request.Direction == TradeDirection.Long && request.Side != OrderSide.Buy
            || request.Direction == TradeDirection.Short && request.Side != OrderSide.Sell)
            return Rejected("the futures order side does not match the intended position direction");

        // Set leverage is idempotent for the symbol and must succeed before an opening order.
        if (request.Direction is TradeDirection.Long or TradeDirection.Short)
        {
            var (leverageStatus, leverageBody, leverageHash) = await SendRawSignedWithHashAsync(
                HttpMethod.Post, "/fapi/v1/leverage",
                new[]
                {
                    new KeyValuePair<string, string>("symbol", request.Symbol.Trim().ToUpperInvariant()),
                    new KeyValuePair<string, string>("leverage", request.Leverage.ToString(CultureInfo.InvariantCulture)),
                },
                venueCreds, cancellationToken);

            if (leverageStatus != HttpStatusCode.OK)
            {
                var detail = DescribeError(leverageBody, leverageStatus);
                return leverageStatus >= HttpStatusCode.InternalServerError
                    ? Ambiguous($"the leverage request to {Venue} was ambiguous ({leverageStatus}): {detail}", leverageHash, Sha256(leverageBody))
                    : Rejected($"the leverage request to {Venue} was rejected ({leverageStatus}): {detail}", leverageHash, Sha256(leverageBody));
            }
        }

        var parameters = new List<KeyValuePair<string, string>>
        {
            new("symbol", request.Symbol.Trim().ToUpperInvariant()),
            new("side", request.Side == OrderSide.Buy ? "BUY" : "SELL"),
            new("type", MapOrderType(request.Type)),
            new("quantity", BinanceJson.Number(request.Quantity)),
            new("positionSide", request.Direction == TradeDirection.Short ? "SHORT" : "LONG"),
            // Binance error -1106: `reduceOnly` may ONLY be sent when it is required (a
            // closing order). Sending `reduceOnly=false` on an entry is itself a rejection,
            // so the parameter is omitted entirely unless this order closes a position.
            new("newClientOrderId", request.ClientOrderId),
            new("newOrderRespType", "RESULT"),
        };
        if (request.Direction is not (TradeDirection.Long or TradeDirection.Short))
        {
            parameters.Add(new("reduceOnly", "true"));
        }

        if (request.Type != OrderType.Market)
        {
            var limitPrice = request.LimitPrice
                             ?? throw new InvalidOperationException(
                                 $"A {request.Type} order requires a limit price.");
            parameters.Add(new("price", BinanceJson.Number(limitPrice)));
            parameters.Add(new("timeInForce", MapTimeInForce(request.TimeInForce ?? TimeInForce.GoodTillCancel)));
        }

        if (request.TakeProfitPrice is { } tp)
        {
            parameters.Add(new("takeProfit", BinanceJson.Number(tp)));
        }
        if (request.StopLossPrice is { } sl)
        {
            parameters.Add(new("stopLoss", BinanceJson.Number(sl)));
        }

        return await SendSignedAsync(
            HttpMethod.Post, "/fapi/v1/order", parameters, venueCreds, request.ClientOrderId, cancellationToken);
    }

    /// <inheritdoc/>
    public async Task<BrokerPlacement> ReconcileAsync(
        string symbol,
        string clientOrderId,
        VenueCredentials? credentials = null,
        CancellationToken cancellationToken = default)
    {
        var venueCreds = ResolveCredentials(credentials);
        if (venueCreds is not { HasCredentials: true })
            return Rejected($"no API credentials are configured for {Venue}; the order cannot be reconciled");

        var parameters = new List<KeyValuePair<string, string>>
        {
            new("symbol", symbol.Trim().ToUpperInvariant()),
            new("origClientOrderId", clientOrderId),
        };
        return await SendSignedAsync(
            HttpMethod.Get, "/fapi/v1/order", parameters, venueCreds, clientOrderId, cancellationToken);
    }

    /// <inheritdoc/>
    public async Task<decimal?> GetAvailableBalanceAsync(
        string quoteAsset,
        VenueCredentials? credentials = null,
        CancellationToken cancellationToken = default)
    {
        var venueCreds = ResolveCredentials(credentials);
        if (venueCreds is not { HasCredentials: true })
            return null;

        try
        {
            // No params needed — the signed query builder appends recvWindow + timestamp automatically.
            var emptyParams = Array.Empty<KeyValuePair<string, string>>();
            var (status, body) = await SendRawSignedAsync(
                HttpMethod.Get, "/fapi/v2/balance", emptyParams, venueCreds, cancellationToken);

            if (status != HttpStatusCode.OK)
                return null;

            using var document = JsonDocument.Parse(body);
            // /fapi/v2/balance returns a plain array of asset balances (the account
            // object's "assets" shape is /fapi/v2/account). Accept both.
            var assets = document.RootElement.ValueKind == JsonValueKind.Array
                ? document.RootElement
                : document.RootElement.TryGetProperty("assets", out var nested)
                    && nested.ValueKind == JsonValueKind.Array
                    ? nested
                    : default(JsonElement?);

            if (assets is not { } assetList)
                return null;

            foreach (var asset in assetList.EnumerateArray())
            {
                var assetName = asset.TryGetProperty("asset", out var name) ? name.GetString() : null;
                if (!string.Equals(assetName, quoteAsset, StringComparison.OrdinalIgnoreCase))
                    continue;

                if (asset.TryGetProperty("balance", out var balanceElement)
                    && decimal.TryParse(balanceElement.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var balance))
                    return balance;
            }

            // The venue answered and does not list the USDT asset: a real zero, not an unknown.
            return 0m;
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            _logger.LogWarning(exception, "{Venue} could not be asked for the {Asset} balance", Venue, quoteAsset);
            return null;
        }
    }

    // ── signed transport ─────────────────────────────────────────────────────────

    /// <summary>Picks the passed-in credentials, falling back to the server's env-var credentials for this venue.</summary>
    private VenueCredentials? ResolveCredentials(VenueCredentials? credentials)
    {
        if (credentials is not null)
            return credentials;

        var venueOptions = _options.For(Venue);
        return venueOptions is { HasCredentials: true }
            ? new VenueCredentials(venueOptions.ApiKey, venueOptions.ApiSecret)
            : null;
    }

    private async Task<BrokerPlacement> SendSignedAsync(
        HttpMethod method,
        string path,
        IReadOnlyList<KeyValuePair<string, string>> parameters,
        VenueCredentials credentials,
        string clientOrderId,
        CancellationToken cancellationToken)
    {
        string body;
        HttpStatusCode status;
        string requestHash;

        try
        {
            (status, body, requestHash) = await SendRawSignedWithHashAsync(
                method, path, parameters, credentials, cancellationToken);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return Ambiguous(
                $"the request to {Venue} timed out; {clientOrderId} may or may not exist at the venue and " +
                $"must be reconciled before anything else is placed");
        }
        catch (HttpRequestException exception)
        {
            return Ambiguous(
                $"the request to {Venue} failed in transport ({exception.Message}); {clientOrderId} must be " +
                $"reconciled before anything else is placed");
        }

        var responseHash = Sha256(body);

        if (status == HttpStatusCode.OK)
            return ParseFuturesOrderResponse(body, requestHash, responseHash, clientOrderId);

        var detail = DescribeError(body, status);

        if ((int)status >= 500)
        {
            return Ambiguous(
                $"{Venue} answered {(int)status}: {detail}. {clientOrderId} must be reconciled before " +
                "anything else is placed.", requestHash, responseHash);
        }

        return Rejected($"{Venue} rejected the order ({(int)status}): {detail}", requestHash, responseHash);
    }

    private async Task<(HttpStatusCode Status, string Body)> SendRawSignedAsync(
        HttpMethod method,
        string path,
        IReadOnlyList<KeyValuePair<string, string>> parameters,
        VenueCredentials credentials,
        CancellationToken cancellationToken)
    {
        var (status, body, _) = await SendRawSignedWithHashAsync(
            method, path, parameters, credentials, cancellationToken);
        return (status, body);
    }

    private async Task<(HttpStatusCode Status, string Body, string RequestHash)> SendRawSignedWithHashAsync(
        HttpMethod method,
        string path,
        IReadOnlyList<KeyValuePair<string, string>> parameters,
        VenueCredentials credentials,
        CancellationToken cancellationToken)
    {
        var client = _http.CreateClient(TradingHttpClients.ForVenue(Venue));
        var timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString(CultureInfo.InvariantCulture);
        var query = BuildQuery(parameters, timestamp);
        var signature = Sign(query, credentials.ApiSecret);
        var signedQuery = $"{query}&signature={signature}";

        var requestHash = Sha256($"{method.Method} {path}?{query}");
        using var message = new HttpRequestMessage(method, $"{path}?{signedQuery}");
        message.Headers.Add("X-MBX-APIKEY", credentials.ApiKey);

        try
        {
            using var response = await client.SendAsync(message, cancellationToken);
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            return (response.StatusCode, body, requestHash);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return (HttpStatusCode.RequestTimeout, string.Empty, requestHash);
        }
        catch (HttpRequestException)
        {
            throw;
        }
    }

    private string BuildQuery(IReadOnlyList<KeyValuePair<string, string>> parameters, string timestamp)
    {
        var builder = new StringBuilder();
        foreach (var (key, value) in parameters)
        {
            if (builder.Length > 0)
                builder.Append('&');
            builder.Append(Uri.EscapeDataString(key)).Append('=').Append(Uri.EscapeDataString(value));
        }
        if (builder.Length > 0)
            builder.Append('&');
        builder.Append("recvWindow=").Append(_options.RecvWindowMs.ToString(CultureInfo.InvariantCulture));
        builder.Append("&timestamp=").Append(timestamp);
        return builder.ToString();
    }

    private BrokerPlacement ParseFuturesOrderResponse(string body, string requestHash, string responseHash, string clientOrderId)
    {
        using var document = JsonDocument.Parse(body);
        var root = document.RootElement;

        // Futures order response: orderId, symbol, status, clientOrderId, price, avgPrice,
        // cumQty, executedQty, closePosition, side, positionSide, etc.
        var venueOrderId = root.TryGetProperty("orderId", out var orderIdElement)
            ? orderIdElement.ToString()
            : null;

        var status = MapStatus(root.TryGetProperty("status", out var statusElement)
            ? statusElement.GetString()
            : null);

        var filled = BinanceJson.DecimalOrDefault(root, "executedQty", 0m);
        var avgPrice = root.TryGetProperty("avgPrice", out var avgElement)
            && decimal.TryParse(avgElement.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var avg)
            ? (decimal?)avg
            : null;

        var fills = new List<BrokerFill>();
        // Futures /fapi v1/order?newOrderRespType=RESULT does not return a fills array;
        // the aggregate quantities are top-level. A single synthetic fill captures the lot.
        if (filled > 0 && avgPrice > 0)
        {
            fills.Add(new BrokerFill(
                VenueTradeId: venueOrderId ?? clientOrderId,
                Price: avgPrice ?? 0m,
                Quantity: filled,
                Fee: 0m,
                FeeAsset: "USDT",
                ExecutedAt: root.TryGetProperty("updateTime", out var updateTime)
                    ? BinanceJson.Timestamp(updateTime, "updateTime")
                    : DateTimeOffset.UtcNow,
                IsMaker: null));
        }

        var outcome = status == ExchangeOrderStatus.Rejected ? BrokerOutcome.Rejected : BrokerOutcome.Accepted;

        return new BrokerPlacement(
            outcome, status, venueOrderId, filled, avgPrice, fills,
            requestHash, responseHash,
            Detail: null,
            VenueUpdatedAt: root.TryGetProperty("updateTime", out var updated)
                ? BinanceJson.Timestamp(updated, "updateTime")
                : null);
    }

    private static string MapOrderType(OrderType type) => type switch
    {
        OrderType.Market => "MARKET",
        OrderType.Limit => "LIMIT",
        OrderType.StopLoss => "STOP_MARKET",
        OrderType.StopLossLimit => "STOP",
        OrderType.TakeProfit => "TAKE_PROFIT_MARKET",
        OrderType.TakeProfitLimit => "TAKE_PROFIT",
        _ => throw new ArgumentOutOfRangeException(nameof(type), type, "Unsupported futures order type."),
    };

    private static string MapTimeInForce(TimeInForce timeInForce) => timeInForce switch
    {
        TimeInForce.GoodTillCancel => "GTC",
        TimeInForce.ImmediateOrCancel => "IOC",
        TimeInForce.FillOrKill => "FOK",
        _ => throw new ArgumentOutOfRangeException(nameof(timeInForce), timeInForce, "Unsupported time in force."),
    };

    private static ExchangeOrderStatus MapStatus(string? status) => status switch
    {
        "NEW" or "PARTIALLY_FILLED" => ExchangeOrderStatus.PartiallyFilled,
        "FILLED" => ExchangeOrderStatus.Filled,
        "CANCELED" => ExchangeOrderStatus.Cancelled,
        "REJECTED" or "EXPIRED" or "EXPIRED_IN_MATCH" => ExchangeOrderStatus.Expired,
        _ => ExchangeOrderStatus.Unknown,
    };

    private static string DescribeError(string body, HttpStatusCode status)
    {
        try
        {
            using var document = JsonDocument.Parse(body);
            var root = document.RootElement;
            var code = root.TryGetProperty("code", out var codeElement) ? codeElement.ToString() : null;
            var message = root.TryGetProperty("msg", out var msgElement) ? msgElement.GetString() : null;
            if (message is not null)
                return code is not null ? $"{message} (code {code})" : message;
        }
        catch (JsonException) { }
        return $"HTTP {(int)status}";
    }

    private static BrokerPlacement Rejected(string detail, string? requestHash = null, string? responseHash = null) =>
        new(BrokerOutcome.Rejected, ExchangeOrderStatus.Rejected, null, 0m, null, [], requestHash, responseHash, detail);

    private static BrokerPlacement Ambiguous(string detail, string? requestHash = null, string? responseHash = null) =>
        new(BrokerOutcome.Ambiguous, ExchangeOrderStatus.Unknown, null, 0m, null, [], requestHash, responseHash, detail);

    private static string Sign(string query, string secret) =>
        Convert.ToHexStringLower(
            HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret), Encoding.UTF8.GetBytes(query)));

    private static string Sha256(string value) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}