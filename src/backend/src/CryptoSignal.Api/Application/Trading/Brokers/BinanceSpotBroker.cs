using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Options;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Brokers;

/// <summary>
/// Places real orders on a Binance-compatible spot venue over signed REST.
/// </summary>
/// <remarks>
/// <para>
/// <b>Spot only, so a SHORT is refused before anything is sent.</b> Selling base currency the account does
/// not hold requires margin, which this platform does not enable — the refusal is arithmetic, not policy,
/// and it happens here rather than at the venue so the rejection names the real reason.
/// </para>
/// <para>
/// <b>An unanswered write is ambiguous, never assumed.</b> A timeout, a cancelled socket or a 5xx leaves the
/// venue possibly holding the order. This class reports <see cref="BrokerOutcome.Ambiguous"/>, and the tick
/// executor turns that into a bot fault so nothing further is placed until a human or a reconcile settles
/// it. Retrying blind is how one intent becomes two positions.
/// </para>
/// <para>
/// <b>The signature covers the exact query string that is sent</b> — same order, same encoding, no
/// re-serialisation between signing and sending. The secret is used for HMAC only: never logged, never
/// hashed into the audit record, never returned. Request and response are persisted as SHA-256 hashes, so a
/// dispute can prove what was sent without the store holding a replayable, signed order.
/// </para>
/// </remarks>
public abstract class BinanceSpotBroker(
    IHttpClientFactory httpClientFactory,
    IOptions<ExchangeOptions> options,
    ILogger logger) : IBroker
{
    public abstract MarketVenue Venue { get; }
    public abstract string Name { get; }

    /// <summary>
    /// SANDBOX on this broker's own venue, and nothing else.
    /// </summary>
    /// <remarks>
    /// Deliberately never PAPER: a paper bot that reached a real venue would place real orders under a mode
    /// the operator was told places none. Deliberately never LIVE either — gates 6-8 of the safety policy
    /// are not implemented, so no code path here may claim to satisfy them.
    /// </remarks>
    public bool Supports(OperatingMode mode, MarketVenue venue) =>
        mode == OperatingMode.Sandbox && venue == Venue;

    public async Task<BrokerPlacement> PlaceAsync(
        BrokerOrderRequest request,
        CancellationToken cancellationToken)
    {
        var venueOptions = options.Value.For(Venue);

        if (!venueOptions.HasCredentials)
        {
            // Fail-closed: no credentials means this venue cannot be traded, not that it should be tried.
            return Rejected(
                $"no API credentials are configured for {Venue}; set Exchange__{Venue}__ApiKey and " +
                $"Exchange__{Venue}__ApiSecret in the server environment");
        }

        if (request.Direction == TradeDirection.Short && request.Side == OrderSide.Sell)
        {
            return Rejected(
                "a spot venue cannot open a SHORT: selling borrowed base currency requires margin, which " +
                "this platform does not enable");
        }

        var validation = ValidateAgainstRules(request);
        if (validation is not null)
            return Rejected(validation);

        var parameters = new List<KeyValuePair<string, string>>
        {
            new("symbol", request.Symbol.Trim().ToUpperInvariant()),
            new("side", request.Side == OrderSide.Buy ? "BUY" : "SELL"),
            new("type", MapOrderType(request.Type)),
            new("quantity", BinanceJson.Number(request.Quantity)),
            new("newClientOrderId", request.ClientOrderId),
            // The venue's own idempotency handle. FULL rather than ACK so the fills come back on the same
            // response — a second round trip to fetch them is another chance to lose the answer.
            new("newOrderRespType", "FULL"),
        };

        if (request.Type != OrderType.Market)
        {
            var limitPrice = request.LimitPrice
                             ?? throw new InvalidOperationException(
                                 $"A {request.Type} order requires a limit price.");
            parameters.Add(new KeyValuePair<string, string>("price", BinanceJson.Number(limitPrice)));
            parameters.Add(new KeyValuePair<string, string>(
                "timeInForce", MapTimeInForce(request.TimeInForce ?? Domain.Enums.Trading.TimeInForce.GoodTillCancel)));
        }

        return await SendSignedAsync(
            HttpMethod.Post, "/api/v3/order", parameters, venueOptions, request.ClientOrderId, cancellationToken);
    }

    /// <summary>
    /// Asks the venue what became of one client order id — the only correct answer to an ambiguous write.
    /// </summary>
    /// <remarks>
    /// Queried by <c>origClientOrderId</c> rather than by venue order id precisely because an ambiguous
    /// write is one where no venue order id came back. The client order id is deterministic from the
    /// decision, so it is knowable without the venue's answer, which is what makes the question askable at
    /// all.
    /// </remarks>
    public async Task<BrokerPlacement> ReconcileAsync(
        string symbol,
        string clientOrderId,
        CancellationToken cancellationToken)
    {
        var venueOptions = options.Value.For(Venue);

        if (!venueOptions.HasCredentials)
            return Rejected($"no API credentials are configured for {Venue}; the order cannot be reconciled");

        var parameters = new List<KeyValuePair<string, string>>
        {
            new("symbol", symbol.Trim().ToUpperInvariant()),
            new("origClientOrderId", clientOrderId),
        };

        var placement = await SendSignedAsync(
            HttpMethod.Get, "/api/v3/order", parameters, venueOptions, clientOrderId, cancellationToken);

        logger.LogWarning(
            "Reconciled {ClientOrderId} on {Venue}: outcome {Outcome}, status {Status}, filled {Filled}",
            clientOrderId, Venue, placement.Outcome, placement.Status, placement.FilledQuantity);

        return placement;
    }

    /// <summary>
    /// Free balance of the quote asset, or <c>null</c> when the venue could not be asked.
    /// </summary>
    /// <remarks>
    /// Null means "unknown" and the risk engine denies on it. That is the intended reading: an unreachable
    /// venue is not an empty account, and it is certainly not an unlimited one.
    /// </remarks>
    public async Task<decimal?> GetAvailableBalanceAsync(string quoteAsset, CancellationToken cancellationToken)
    {
        var venueOptions = options.Value.For(Venue);
        if (!venueOptions.HasCredentials)
            return null;

        try
        {
            var (status, body) = await SendRawSignedAsync(
                HttpMethod.Get, "/api/v3/account", [], venueOptions, cancellationToken);

            if (status != HttpStatusCode.OK)
            {
                logger.LogWarning("{Venue} refused the balance request with {Status}", Venue, status);
                return null;
            }

            using var document = JsonDocument.Parse(body);
            if (!document.RootElement.TryGetProperty("balances", out var balances)
                || balances.ValueKind != JsonValueKind.Array)
            {
                return null;
            }

            foreach (var balance in balances.EnumerateArray())
            {
                var asset = balance.TryGetProperty("asset", out var assetElement) ? assetElement.GetString() : null;
                if (!string.Equals(asset, quoteAsset, StringComparison.OrdinalIgnoreCase))
                    continue;

                // "free" only. Funds locked in resting orders are not available to a new one, and counting
                // them would let the risk engine authorise an order the venue then refuses for insufficient
                // balance.
                return BinanceJson.DecimalOrDefault(balance, "free", 0m);
            }

            // The venue answered and does not list the asset: a real zero, not an unknown.
            return 0m;
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            logger.LogWarning(exception, "{Venue} could not be asked for the {Asset} balance", Venue, quoteAsset);
            return null;
        }
    }

    // ── signed transport ─────────────────────────────────────────────────────────

    private async Task<BrokerPlacement> SendSignedAsync(
        HttpMethod method,
        string path,
        IReadOnlyList<KeyValuePair<string, string>> parameters,
        BinanceVenueOptions venueOptions,
        string clientOrderId,
        CancellationToken cancellationToken)
    {
        string body;
        HttpStatusCode status;
        string requestHash;

        try
        {
            (status, body, requestHash) = await SendRawSignedWithHashAsync(
                method, path, parameters, venueOptions, cancellationToken);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // A client-side timeout. The request may well have reached the venue — this is exactly the
            // ambiguity that must never be guessed at.
            return Ambiguous(
                $"the request to {Venue} timed out; {clientOrderId} may or may not exist at the venue and " +
                "must be reconciled before anything else is placed");
        }
        catch (HttpRequestException exception)
        {
            // A transport failure after the bytes left this process is equally unknowable. Treated as
            // ambiguous rather than rejected: assuming "not placed" is the assumption that doubles positions.
            return Ambiguous(
                $"the request to {Venue} failed in transport ({exception.Message}); {clientOrderId} must be " +
                "reconciled before anything else is placed");
        }

        var responseHash = Sha256(body);

        if (status == HttpStatusCode.OK)
            return ParseOrderResponse(body, requestHash, responseHash);

        // 4xx is the venue speaking: it read the order and refused it, so nothing is pending. 5xx is the
        // venue failing to answer, which says nothing about whether it accepted the order first.
        var detail = DescribeError(body, status);

        if ((int)status >= 500)
        {
            return Ambiguous(
                $"{Venue} answered {(int)status}: {detail}. {clientOrderId} must be reconciled before " +
                "anything else is placed.",
                requestHash, responseHash);
        }

        return Rejected($"{Venue} rejected the order ({(int)status}): {detail}", requestHash, responseHash);
    }

    private async Task<(HttpStatusCode Status, string Body)> SendRawSignedAsync(
        HttpMethod method,
        string path,
        IReadOnlyList<KeyValuePair<string, string>> parameters,
        BinanceVenueOptions venueOptions,
        CancellationToken cancellationToken)
    {
        var (status, body, _) = await SendRawSignedWithHashAsync(
            method, path, parameters, venueOptions, cancellationToken);
        return (status, body);
    }

    private async Task<(HttpStatusCode Status, string Body, string RequestHash)> SendRawSignedWithHashAsync(
        HttpMethod method,
        string path,
        IReadOnlyList<KeyValuePair<string, string>> parameters,
        BinanceVenueOptions venueOptions,
        CancellationToken cancellationToken)
    {
        var client = httpClientFactory.CreateClient(TradingHttpClients.ForVenue(Venue));

        var builder = new StringBuilder();
        foreach (var (key, value) in parameters)
        {
            if (builder.Length > 0)
                builder.Append('&');
            builder.Append(Uri.EscapeDataString(key)).Append('=').Append(Uri.EscapeDataString(value));
        }

        if (builder.Length > 0)
            builder.Append('&');

        // recvWindow bounds how long a captured request stays replayable at the venue; the timestamp is what
        // it is measured against, so both are appended last and signed with everything else.
        builder.Append("recvWindow=").Append(options.Value.RecvWindowMs.ToString(CultureInfo.InvariantCulture));
        builder.Append("&timestamp=")
            .Append(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString(CultureInfo.InvariantCulture));

        var query = builder.ToString();
        var signature = Sign(query, venueOptions.ApiSecret);

        // Signed over exactly these bytes, then sent as exactly these bytes. Rebuilding the query from a
        // dictionary after signing is the classic way to sign one string and send another.
        var signedQuery = $"{query}&signature={signature}";

        // The hash covers the unsigned query only. The signature is a MAC of the secret; storing it would
        // put a replayable credential artefact in the audit trail, which the audit trail exists to avoid.
        var requestHash = Sha256($"{method.Method} {path}?{query}");

        using var message = new HttpRequestMessage(method, $"{path}?{signedQuery}");
        message.Headers.Add("X-MBX-APIKEY", venueOptions.ApiKey);

        using var response = await client.SendAsync(message, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);

        return (response.StatusCode, body, requestHash);
    }

    private BrokerPlacement ParseOrderResponse(string body, string requestHash, string responseHash)
    {
        using var document = JsonDocument.Parse(body);
        var root = document.RootElement;

        var venueOrderId = root.TryGetProperty("orderId", out var orderIdElement)
            ? orderIdElement.ToString()
            : null;

        var status = MapStatus(root.TryGetProperty("status", out var statusElement)
            ? statusElement.GetString()
            : null);

        var filled = BinanceJson.DecimalOrDefault(root, "executedQty", 0m);
        var quoteFilled = BinanceJson.DecimalOrDefault(root, "cummulativeQuoteQty", 0m);

        var fills = new List<BrokerFill>();
        if (root.TryGetProperty("fills", out var fillsElement) && fillsElement.ValueKind == JsonValueKind.Array)
        {
            var index = 0;
            foreach (var element in fillsElement.EnumerateArray())
            {
                var price = BinanceJson.DecimalOrDefault(element, "price", 0m);
                var quantity = BinanceJson.DecimalOrDefault(element, "qty", 0m);
                var commission = BinanceJson.DecimalOrDefault(element, "commission", 0m);
                var commissionAsset = element.TryGetProperty("commissionAsset", out var assetElement)
                    ? assetElement.GetString() ?? string.Empty
                    : string.Empty;

                // A venue trade id is the fill's identity and the unique index's key. When the venue omits
                // it — market fills sometimes carry none — it is synthesised from the order id and the fill's
                // position, which is stable across a re-read of the same order and so still idempotent.
                var tradeId = element.TryGetProperty("tradeId", out var tradeIdElement)
                              && tradeIdElement.ValueKind is not JsonValueKind.Null
                    ? tradeIdElement.ToString()
                    : $"{venueOrderId ?? "unknown"}-{index}";

                fills.Add(new BrokerFill(
                    VenueTradeId: tradeId,
                    Price: price,
                    Quantity: quantity,
                    Fee: commission,
                    FeeAsset: commissionAsset,
                    ExecutedAt: root.TryGetProperty("transactTime", out var transactElement)
                        ? BinanceJson.Timestamp(transactElement, "transactTime")
                        : DateTimeOffset.UtcNow,
                    IsMaker: null));

                index++;
            }
        }

        // Averaged from the venue's own cumulative quote quantity where it reported one, which already
        // accounts for fills at several prices; the per-fill average is the fallback.
        decimal? averagePrice = filled > 0 && quoteFilled > 0
            ? quoteFilled / filled
            : fills.Count > 0 && filled > 0
                ? fills.Sum(f => f.Price * f.Quantity) / filled
                : null;

        var outcome = status == ExchangeOrderStatus.Rejected ? BrokerOutcome.Rejected : BrokerOutcome.Accepted;

        return new BrokerPlacement(
            outcome, status, venueOrderId, filled, averagePrice, fills,
            requestHash, responseHash,
            Detail: null,
            VenueUpdatedAt: root.TryGetProperty("transactTime", out var updated)
                ? BinanceJson.Timestamp(updated, "transactTime")
                : null);
    }

    // ── helpers ──────────────────────────────────────────────────────────────────

    private string? ValidateAgainstRules(BrokerOrderRequest request)
    {
        var rules = request.Rules;

        if (!rules.IsTradable)
            return $"{request.Symbol} is not tradable on {request.Venue}";

        if (request.Quantity <= 0)
            return "quantity must be positive";

        if (rules.MinQuantity > 0 && request.Quantity < rules.MinQuantity)
            return $"quantity {BinanceJson.Number(request.Quantity)} is below the venue minimum {BinanceJson.Number(rules.MinQuantity)}";

        if (!InstrumentRules.IsOnGrid(request.Quantity, rules.StepSize))
            return $"quantity {BinanceJson.Number(request.Quantity)} is not a multiple of the step size {BinanceJson.Number(rules.StepSize)}";

        if (rules.MinNotional > 0 && request.ReferencePrice > 0)
        {
            var notional = request.Quantity * request.ReferencePrice;
            if (notional < rules.MinNotional)
                return $"notional {BinanceJson.Number(notional)} is below the venue minimum {BinanceJson.Number(rules.MinNotional)}";
        }

        return null;
    }

    private static string MapOrderType(OrderType type) => type switch
    {
        OrderType.Market => "MARKET",
        OrderType.Limit => "LIMIT",
        OrderType.StopLoss => "STOP_LOSS",
        OrderType.StopLossLimit => "STOP_LOSS_LIMIT",
        OrderType.TakeProfit => "TAKE_PROFIT",
        OrderType.TakeProfitLimit => "TAKE_PROFIT_LIMIT",
        _ => throw new ArgumentOutOfRangeException(nameof(type), type, "Unsupported order type."),
    };

    private static string MapTimeInForce(Domain.Enums.Trading.TimeInForce timeInForce) => timeInForce switch
    {
        Domain.Enums.Trading.TimeInForce.GoodTillCancel => "GTC",
        Domain.Enums.Trading.TimeInForce.ImmediateOrCancel => "IOC",
        Domain.Enums.Trading.TimeInForce.FillOrKill => "FOK",
        _ => throw new ArgumentOutOfRangeException(nameof(timeInForce), timeInForce, "Unsupported time in force."),
    };

    /// <summary>
    /// Maps the venue's status word. An unrecognised one becomes <see cref="ExchangeOrderStatus.Unknown"/>,
    /// never <c>Filled</c> — a status this code does not understand is not evidence of a fill.
    /// </summary>
    private static ExchangeOrderStatus MapStatus(string? status) => status switch
    {
        "NEW" or "PENDING_NEW" => ExchangeOrderStatus.New,
        "PARTIALLY_FILLED" => ExchangeOrderStatus.PartiallyFilled,
        "FILLED" => ExchangeOrderStatus.Filled,
        "CANCELED" or "PENDING_CANCEL" => ExchangeOrderStatus.Cancelled,
        "REJECTED" => ExchangeOrderStatus.Rejected,
        "EXPIRED" or "EXPIRED_IN_MATCH" => ExchangeOrderStatus.Expired,
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
        catch (JsonException)
        {
            // Not JSON — fall through to the status line rather than surfacing a raw HTML error page.
        }

        return $"HTTP {(int)status}";
    }

    private static BrokerPlacement Rejected(string detail, string? requestHash = null, string? responseHash = null) =>
        new(BrokerOutcome.Rejected, ExchangeOrderStatus.Rejected, VenueOrderId: null,
            FilledQuantity: 0m, AverageFillPrice: null, Fills: [],
            RequestHash: requestHash, ResponseHash: responseHash, Detail: detail);

    private static BrokerPlacement Ambiguous(string detail, string? requestHash = null, string? responseHash = null) =>
        new(BrokerOutcome.Ambiguous, ExchangeOrderStatus.Unknown, VenueOrderId: null,
            FilledQuantity: 0m, AverageFillPrice: null, Fills: [],
            RequestHash: requestHash, ResponseHash: responseHash, Detail: detail);

    private static string Sign(string query, string secret) =>
        Convert.ToHexStringLower(
            HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret), Encoding.UTF8.GetBytes(query)));

    private static string Sha256(string value) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}

/// <summary>The Binance spot testnet adapter — the only venue this platform places real orders on.</summary>
/// <remarks>
/// Its credentials are server-side environment values (<c>Exchange__BinanceTestnet__ApiKey</c> /
/// <c>ApiSecret</c>) and never appear in a response body or reach the browser.
/// </remarks>
public sealed class BinanceTestnetBroker(
    IHttpClientFactory httpClientFactory,
    IOptions<ExchangeOptions> options,
    ILogger<BinanceTestnetBroker> logger)
    : BinanceSpotBroker(httpClientFactory, options, logger), IScopedSvcMarker
{
    public override MarketVenue Venue => MarketVenue.BinanceTestnet;
    public override string Name => "binance-testnet";
}
