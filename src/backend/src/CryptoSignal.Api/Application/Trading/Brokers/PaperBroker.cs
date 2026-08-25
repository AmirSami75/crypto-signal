using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Options;
using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Brokers;

/// <summary>
/// The PAPER simulator: fills every accepted order deterministically, places nothing anywhere, and is the
/// platform's default execution path.
/// </summary>
/// <remarks>
/// <para>
/// <b>It refuses whatever the venue would refuse.</b> The instrument grid, the minimum notional, the
/// tradable flag, market-order support and the bot's own slippage tolerance are all enforced here, on the
/// rules that travelled with the request. A simulator that filled orders the venue rejects produces a
/// paper track record nobody can reproduce in sandbox, which is worse than no track record: it reads as
/// evidence.
/// </para>
/// <para>
/// <b>The fill price is the reference price moved against the order.</b> A market order placed on a closed
/// candle actually fills somewhere in the next candle, which does not exist yet at decision time — so the
/// gap between the close the model saw and the open the order would have got is charged as slippage rather
/// than waited for. Adverse-only, never favourable: optimism here is how a paper account invents profit.
/// </para>
/// <para>
/// <b>Deterministic by construction.</b> No clock and no randomness enter the price, and the venue trade id
/// is derived from the client order id, so replaying the same tick produces byte-identical fills — and the
/// unique <c>(Venue, VenueTradeId)</c> index makes a retried placement idempotent instead of doubling the
/// position.
/// </para>
/// </remarks>
public sealed class PaperBroker(
    IOptions<PaperBrokerOptions> options,
    ILogger<PaperBroker> logger) : IBroker, IScopedSvcMarker
{
    public string Name => "paper";

    /// <summary>
    /// PAPER on every venue, and PAPER only.
    /// </summary>
    /// <remarks>
    /// Correct on any venue because it never contacts one — the venue only selects which grid the request
    /// was sized against. Never claiming SANDBOX or LIVE is the other half: a mode meant to reach a real
    /// venue must never be silently satisfied by a simulator.
    /// </remarks>
    public bool Supports(OperatingMode mode, MarketVenue venue) => mode == OperatingMode.Paper;

    public Task<BrokerPlacement> PlaceAsync(BrokerOrderRequest request, CancellationToken cancellationToken)
    {
        var rejection = Validate(request);
        if (rejection is not null)
        {
            logger.LogInformation(
                "Paper broker rejected {ClientOrderId} for {Symbol}: {Reason}",
                request.ClientOrderId, request.Symbol, rejection);

            return Task.FromResult(new BrokerPlacement(
                BrokerOutcome.Rejected, ExchangeOrderStatus.Rejected, VenueOrderId: null,
                FilledQuantity: 0m, AverageFillPrice: null, Fills: [],
                Detail: rejection));
        }

        var slippageBps = options.Value.SlippageBps;
        var fillPrice = ApplySlippage(request.ReferencePrice, request.Side, slippageBps, request.Rules);
        var quantity = request.Quantity;
        var notional = fillPrice * quantity;

        // Charged in the quote asset on both sides. The venue takes its fee in the asset received, but a
        // paper account whose costs are split across two currencies cannot report one P&L series, and at
        // these sizes the difference is a rounding artefact rather than a distortion.
        var fee = decimal.Round(notional * options.Value.FeeBps / 10_000m, 10, MidpointRounding.AwayFromZero);

        var executedAt = DateTimeOffset.UtcNow;
        var fill = new BrokerFill(
            VenueTradeId: SimulatedTradeId(request.ClientOrderId),
            Price: fillPrice,
            Quantity: quantity,
            Fee: fee,
            FeeAsset: request.Rules.QuoteAsset,
            ExecutedAt: executedAt,
            // A simulated market order is a taker by definition; claiming the maker rebate would be the
            // same optimism as a favourable fill price.
            IsMaker: false);

        logger.LogInformation(
            "Paper broker filled {ClientOrderId}: {Side} {Quantity} {Symbol} at {Price} (reference {Reference}, {Bps} bps adverse), fee {Fee} {FeeAsset}",
            request.ClientOrderId, request.Side, quantity, request.Symbol, fillPrice,
            request.ReferencePrice, slippageBps, fee, request.Rules.QuoteAsset);

        return Task.FromResult(new BrokerPlacement(
            BrokerOutcome.Accepted,
            ExchangeOrderStatus.Filled,
            VenueOrderId: SimulatedOrderId(request.ClientOrderId),
            FilledQuantity: quantity,
            AverageFillPrice: fillPrice,
            Fills: [fill],
            RequestHash: null,
            ResponseHash: null,
            Detail: $"simulated fill {slippageBps} bps adverse to {BinanceNumber(request.ReferencePrice)}",
            VenueUpdatedAt: executedAt));
    }

    /// <summary>
    /// Nothing to reconcile — the simulator cannot produce an ambiguous write, because there is no network
    /// call to time out. Reported as <see cref="ExchangeOrderStatus.Unknown"/> rather than invented.
    /// </summary>
    public Task<BrokerPlacement> ReconcileAsync(
        string symbol,
        string clientOrderId,
        CancellationToken cancellationToken) =>
        Task.FromResult(new BrokerPlacement(
            BrokerOutcome.Rejected, ExchangeOrderStatus.Unknown, VenueOrderId: null,
            FilledQuantity: 0m, AverageFillPrice: null, Fills: [],
            Detail: "the paper simulator holds no order book to reconcile against; its writes cannot be ambiguous"));

    /// <summary>
    /// The configured paper balance — a constant, not a running account.
    /// </summary>
    /// <remarks>
    /// It exists so the risk engine's balance check has a real number to work with instead of "unknown",
    /// which would deny every paper order. Realised paper P&amp;L is tracked on <c>BotPositions</c>, and
    /// this figure deliberately does not move with it: a paper run that stops when a notional wallet empties
    /// stops testing the strategy and starts testing the wallet.
    /// </remarks>
    public Task<decimal?> GetAvailableBalanceAsync(string quoteAsset, CancellationToken cancellationToken) =>
        Task.FromResult<decimal?>(options.Value.QuoteBalance);

    /// <summary>The venue's own refusals, applied to the grid the order was sized against.</summary>
    private string? Validate(BrokerOrderRequest request)
    {
        var rules = request.Rules;

        if (!rules.IsTradable)
            return $"{request.Symbol} is not tradable on {request.Venue}";

        // Every venue this platform reaches is spot, so a SHORT cannot be filled on any of them — a spot
        // account cannot sell what it does not hold. Simulating one would produce paper profits that are
        // unreachable in sandbox, so the simulator refuses exactly where the venue would.
        if (request.Direction == TradeDirection.Short && request.Side == OrderSide.Sell)
        {
            return "a spot venue cannot open a SHORT: selling borrowed base currency requires margin, " +
                   "which this platform does not enable";
        }

        if (request.Type == OrderType.Market && !rules.SupportsMarketOrders)
            return $"{request.Symbol} does not accept market orders on {request.Venue}";

        if (request.Quantity <= 0)
            return "quantity must be positive";

        if (rules.MinQuantity > 0 && request.Quantity < rules.MinQuantity)
            return $"quantity {BinanceNumber(request.Quantity)} is below the venue minimum {BinanceNumber(rules.MinQuantity)}";

        if (rules.MaxQuantity > 0 && request.Quantity > rules.MaxQuantity)
            return $"quantity {BinanceNumber(request.Quantity)} exceeds the venue maximum {BinanceNumber(rules.MaxQuantity)}";

        if (!InstrumentRules.IsOnGrid(request.Quantity, rules.StepSize))
            return $"quantity {BinanceNumber(request.Quantity)} is not a multiple of the step size {BinanceNumber(rules.StepSize)}";

        if (request.LimitPrice is { } limit && !InstrumentRules.IsOnGrid(limit, rules.TickSize))
            return $"limit price {BinanceNumber(limit)} is not a multiple of the tick size {BinanceNumber(rules.TickSize)}";

        if (request.ReferencePrice <= 0)
            return "a positive reference price is required to simulate a fill";

        var notional = request.Quantity * request.ReferencePrice;
        if (rules.MinNotional > 0 && notional < rules.MinNotional)
            return $"notional {BinanceNumber(notional)} is below the venue minimum {BinanceNumber(rules.MinNotional)}";

        // The bot said how much slippage it would tolerate. If the simulator's own modelled slippage exceeds
        // that, a real venue would have refused the fill, so the simulator refuses it too rather than
        // filling at a price the bot declared unacceptable.
        if (request.MaxSlippageBps > 0 && options.Value.SlippageBps > request.MaxSlippageBps)
        {
            return $"modelled slippage {options.Value.SlippageBps} bps exceeds the bot's tolerance " +
                   $"{request.MaxSlippageBps} bps";
        }

        return null;
    }

    /// <summary>Moves the price against the order and back onto the venue's tick grid.</summary>
    private static decimal ApplySlippage(decimal reference, OrderSide side, int slippageBps, InstrumentRules rules)
    {
        var factor = 1m + (side == OrderSide.Buy ? slippageBps : -slippageBps) / 10_000m;
        var slipped = reference * factor;

        // Quantized in the adverse direction on both sides: QuantizePrice truncates downward, which is
        // adverse for a sell but favourable for a buy, so a buy is nudged up to the next tick instead.
        var quantized = rules.QuantizePrice(slipped);

        if (side == OrderSide.Buy && quantized < slipped && rules.TickSize > 0)
            quantized += rules.TickSize;

        return quantized > 0 ? quantized : slipped;
    }

    /// <summary>
    /// A trade id derived from the client order id, so a replayed tick produces the same id.
    /// </summary>
    /// <remarks>
    /// This is what makes the simulator idempotent: the unique <c>(Venue, VenueTradeId)</c> index rejects the
    /// second insert of a re-placed order rather than recording a second fill and doubling the position.
    /// </remarks>
    private static string SimulatedTradeId(string clientOrderId) =>
        "paper-" + Convert.ToHexStringLower(
            SHA256.HashData(Encoding.UTF8.GetBytes("trade:" + clientOrderId)))[..16];

    private static string SimulatedOrderId(string clientOrderId) =>
        "paper-" + Convert.ToHexStringLower(
            SHA256.HashData(Encoding.UTF8.GetBytes("order:" + clientOrderId)))[..16];

    private static string BinanceNumber(decimal value) => MarketData.BinanceJson.Number(value);
}
