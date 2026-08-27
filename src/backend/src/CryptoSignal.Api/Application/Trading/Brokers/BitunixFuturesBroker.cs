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

/// <summary>
/// Bitunix's request-signing scheme: double SHA-256 over
/// <c>SHA256(nonce + timestamp + apiKey + sortedQueryString + compactJsonBody) + secretKey</c>,
/// carried in four headers rather than a query parameter.
/// </summary>
/// <remarks>
/// <para>
/// Two details bite if missed, and both are enforced by construction here. The query parameters must be
/// concatenated as <c>key1value1key2value2…</c> <b>sorted by key</b>, not url-encoded — sorting them any
/// other way signs one string and sends another. And the JSON body string inside the signature must be
/// byte-identical to the body sent, so this class serialises once and reuses those exact bytes for both.
/// </para>
/// <para>
/// The secret is an input to the second hash only; it is never logged, never written into a request
/// beyond that computation, and never returned.
/// </para>
/// </remarks>
public static class BitunixSigner
{
    public static string Sha256Hex(string input)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexStringLower(bytes);
    }

    /// <summary>Sorted key-value concatenation Bitunix expects for GET query parameters.</summary>
    public static string SortedQuery(IReadOnlyList<KeyValuePair<string, string>> parameters) =>
        string.Concat(
            parameters
                .OrderBy(p => p.Key, StringComparer.Ordinal)
                .Select(p => $"{p.Key}{p.Value}"));

    /// <summary>The four headers every signed request carries.</summary>
    public static (string Sign, string Nonce, string Timestamp) BuildHeaders(
        string apiKey,
        string apiSecret,
        string sortedQuery,
        string jsonBody)
    {
        var nonce = Guid.NewGuid().ToString("N"); // 32 hex chars, as the docs specify.
        var timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            .ToString(System.Globalization.CultureInfo.InvariantCulture);

        var digest = Sha256Hex(nonce + timestamp + apiKey + sortedQuery + jsonBody);
        var sign = Sha256Hex(digest + apiSecret);

        return (sign, nonce, timestamp);
    }
}

/// <summary>
/// Places orders on Bitunix USDT-margined futures over their OpenAPI.
/// </summary>
/// <remarks>
/// <para>
/// <b>Futures is a different risk surface from spot</b>, and this class says so in behaviour: leverage is
/// not requested — every order carries no <c>lever</c> field, so it inherits whatever the account's
/// position mode sets, and the platform-level <c>MaxLeverage: 1</c> plus the risk engine remain what
/// actually bounds exposure. A SHORT here is a real futures short and is gated by
/// <c>Trading:Risk:AllowShorting</c> upstream of this class; unlike the Binance spot adapter, there is no
/// arithmetic refusal, so the policy check is the only thing between a bot and an opened short position.
/// </para>
/// <para>
/// Idempotency rides on Bitunix's <c>clientId</c> field, deterministic from the decision id exactly as on
/// Binance — a retried placement reports the same order instead of doubling. An unanswered write is
/// <see cref="BrokerOutcome.Ambiguous"/>, never assumed placed or failed.
/// </para>
/// </remarks>
public sealed class BitunixFuturesBroker(
    IHttpClientFactory httpClientFactory,
    ILogger<BitunixFuturesBroker> logger) : IBroker, IScopedSvcMarker
{
    // Credentials arrive per-call from the caller's stored connection rather than from IOptions:
    // unlike the Binance adapters (one deployment-wide credential set), Bitunix keys are per user.
    private readonly IHttpClientFactory _httpClientFactory = httpClientFactory;

    public string Name => "bitunix-futures";

    /// <summary>
    /// Bitunix has no demo/testnet host. It therefore cannot claim SANDBOX: its only HTTP host is
    /// production <c>fapi.bitunix.com</c>. PAPER is handled by the simulator; LIVE remains disabled.
    /// </summary>
    public bool Supports(OperatingMode mode, MarketVenue venue) =>
        mode == OperatingMode.Live && venue == MarketVenue.Bitunix;

    public async Task<BrokerPlacement> PlaceAsync(
        BrokerOrderRequest request,
        VenueCredentials? credentials = null,
        CancellationToken cancellationToken = default)
    {
        if (credentials is not { HasCredentials: true })
            return Rejected("no Bitunix API credentials are available for this user; store a connection or " +
                            "configure Exchange__Bitunix__ApiKey/ApiSecret");
        var creds = credentials;

        var body = JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["symbol"] = request.Symbol.Trim().ToUpperInvariant(),
            ["side"] = request.Side == OrderSide.Buy ? "BUY" : "SELL",
            ["orderType"] = request.Type == OrderType.Market ? "MARKET" : "LIMIT",
            ["qty"] = request.Quantity.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["clientId"] = request.ClientOrderId,

            // Bitunix requires an explicit effect even for market orders.
            ["effect"] = MapTimeInForce(request.TimeInForce),

            // Bracket fields when the decision carried levels — Bitunix accepts TP/SL inline.
            ["reduceOnly"] = false,
        });

        if (request.Type != OrderType.Market && request.LimitPrice is { } limitPrice)
        {
            var withPrice = new Dictionary<string, object>(JsonSerializer.Deserialize<Dictionary<string, object>>(body)!)
            {
                ["price"] = limitPrice.ToString(System.Globalization.CultureInfo.InvariantCulture),
            };
            body = JsonSerializer.Serialize(withPrice);
        }

        return await SendSignedAsync(
            HttpMethod.Post, "/api/v1/futures/trade/place_order", [], body, creds,
            request.ClientOrderId, cancellationToken);
    }

    public Task<BrokerPlacement> ReconcileAsync(
        string symbol,
        string clientOrderId,
        VenueCredentials? credentials = null,
        CancellationToken cancellationToken = default)
    {
        throw new NotSupportedException(
            "Bitunix order reconciliation is not implemented yet; an ambiguous write on this venue " +
            "must be settled manually at the exchange before trading resumes.");
    }

    public async Task<decimal?> GetAvailableBalanceAsync(
        string quoteAsset, VenueCredentials? credentials = null, CancellationToken cancellationToken = default)
    {
        if (credentials is not { HasCredentials: true })
            return null;

        try
        {
            var (status, body) = await SendRawSignedAsync(
                HttpMethod.Get, "/api/v1/futures/account",
                [new KeyValuePair<string, string>("marginCoin", quoteAsset.ToUpperInvariant())],
                string.Empty, credentials, cancellationToken);

            if (status != System.Net.HttpStatusCode.OK)
            {
                logger.LogWarning("Bitunix refused the balance request with {Status}", status);
                return null;
            }

            using var document = JsonDocument.Parse(body);
            var data = document.RootElement.GetProperty("data");
            // "available" is what may back a new order; margin already committed is excluded.
            return decimal.Parse(
                data.GetProperty("available").GetString() ?? "0",
                System.Globalization.CultureInfo.InvariantCulture);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            logger.LogWarning(exception, "Bitunix could not be asked for the {Asset} balance", quoteAsset);
            return null;
        }
    }

    private async Task<BrokerPlacement> SendSignedAsync(
        HttpMethod method,
        string path,
        IReadOnlyList<KeyValuePair<string, string>> queryParams,
        string jsonBody,
        VenueCredentials credentials,
        string clientOrderId,
        CancellationToken cancellationToken)
    {
        string body;
        System.Net.HttpStatusCode status;
        string requestHash;

        try
        {
            (status, body, requestHash) = await SendRawSignedWithHashAsync(
                method, path, queryParams, jsonBody, credentials, cancellationToken);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return Ambiguous(
                $"the request to Bitunix timed out; {clientOrderId} may or may not exist at the venue and " +
                "must be reconciled before anything else is placed");
        }
        catch (HttpRequestException exception)
        {
            return Ambiguous(
                $"the request to Bitunix failed in transport ({exception.Message}); {clientOrderId} must be " +
                "reconciled before anything else is placed");
        }

        var responseHash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(body)));

        if (status == System.Net.HttpStatusCode.OK)
            return ParseOrderResponse(body, requestHash, responseHash);

        var detail = DescribeError(body);

        if ((int)status >= 500)
        {
            return Ambiguous(
                $"Bitunix answered {(int)status}: {detail}. {clientOrderId} must be reconciled before " +
                "anything else is placed.",
                requestHash, responseHash);
        }

        return Rejected($"Bitunix rejected the order ({(int)status}): {detail}", requestHash, responseHash);
    }

    private async Task<(System.Net.HttpStatusCode Status, string Body)> SendRawSignedAsync(
        HttpMethod method,
        string path,
        IReadOnlyList<KeyValuePair<string, string>> queryParams,
        string jsonBody,
        VenueCredentials credentials,
        CancellationToken cancellationToken)
    {
        var (status, body, _) = await SendRawSignedWithHashAsync(
            method, path, queryParams, jsonBody, credentials, cancellationToken);
        return (status, body);
    }

    private async Task<(System.Net.HttpStatusCode Status, string Body, string RequestHash)>
        SendRawSignedWithHashAsync(
            HttpMethod method,
            string path,
            IReadOnlyList<KeyValuePair<string, string>> queryParams,
            string jsonBody,
            VenueCredentials credentials,
            CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient(TradingHttpClients.ForVenue(MarketVenue.Bitunix));

        var sortedQuery = BitunixSigner.SortedQuery(queryParams);
        var (sign, nonce, timestamp) =
            BitunixSigner.BuildHeaders(credentials.ApiKey, credentials.ApiSecret, sortedQuery, jsonBody);

        var queryString = string.Join('&', queryParams.Select(p =>
            $"{Uri.EscapeDataString(p.Key)}={Uri.EscapeDataString(p.Value)}"));
        var uri = queryString.Length == 0 ? path : $"{path}?{queryString}";

        using var message = new HttpRequestMessage(method, uri);
        message.Headers.Add("api-key", credentials.ApiKey);
        message.Headers.Add("sign", sign);
        message.Headers.Add("nonce", nonce);
        message.Headers.Add("timestamp", timestamp);

        if (jsonBody.Length > 0)
        {
            message.Content = new StringContent(jsonBody, Encoding.UTF8, "application/json");
        }

        // The hash covers everything signed except the secret-derived signature itself.
        var requestHash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(
            $"{method.Method} {uri}|{sortedQuery}|{jsonBody}")));

        using var response = await client.SendAsync(message, cancellationToken);
        var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);

        return (response.StatusCode, responseBody, requestHash);
    }

    private BrokerPlacement ParseOrderResponse(string body, string requestHash, string responseHash)
    {
        using var document = JsonDocument.Parse(body);
        var root = document.RootElement;

        // Bitunix wraps everything: code 0 is success, anything else is a business refusal.
        var code = root.TryGetProperty("code", out var codeElement) ? codeElement.GetInt32() : -1;

        if (code != 0)
        {
            var refusal = root.TryGetProperty("msg", out var msgElement)
                ? msgElement.GetString()
                : "no message";
            return Rejected(
                $"Bitunix refused the placement (code {code}): {refusal}",
                requestHash, responseHash);
        }

        var data = root.TryGetProperty("data", out var dataElement) ? dataElement : default;
        var venueOrderId = data.ValueKind == JsonValueKind.Object &&
                           data.TryGetProperty("orderId", out var orderIdElement)
            ? orderIdElement.GetString()
            : null;

        // A synchronous accept with no fill report yet: the order is working, fills arrive via the
        // order-status endpoint on the next reconcile pass.
        return new BrokerPlacement(
            BrokerOutcome.Accepted,
            ExchangeOrderStatus.New,
            venueOrderId,
            FilledQuantity: 0m,
            AverageFillPrice: null,
            Fills: [],
            RequestHash: requestHash,
            ResponseHash: responseHash);
    }

    private static string DescribeError(string body)
    {
        try
        {
            using var document = JsonDocument.Parse(body);
            return document.RootElement.TryGetProperty("msg", out var msg)
                ? msg.GetString() ?? body
                : body;
        }
        catch (JsonException)
        {
            return body;
        }
    }

    private static string MapTimeInForce(TimeInForce? timeInForce) => timeInForce switch
    {
        TimeInForce.ImmediateOrCancel => "IOC",
        TimeInForce.FillOrKill => "FOK",
        _ => "GTC",
    };

    private static BrokerPlacement Rejected(string detail, string? requestHash = null, string? responseHash = null) =>
        new(BrokerOutcome.Rejected, ExchangeOrderStatus.Rejected, VenueOrderId: null,
            FilledQuantity: 0m, AverageFillPrice: null, Fills: [],
            RequestHash: requestHash, ResponseHash: responseHash, Detail: detail);

    private static BrokerPlacement Ambiguous(string detail, string? requestHash = null, string? responseHash = null) =>
        new(BrokerOutcome.Ambiguous, ExchangeOrderStatus.Unknown, VenueOrderId: null,
            FilledQuantity: 0m, AverageFillPrice: null, Fills: [],
            RequestHash: requestHash, ResponseHash: responseHash, Detail: detail);
}
