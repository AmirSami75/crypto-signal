using Asp.Versioning;
using CryptoSignal.Api.Application.DTOs.Trading;
using CryptoSignal.Api.Application.Options;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.Execution;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Clients;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Common;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.API.Controllers.v1.Trading;

/// <summary>
/// On-demand signals: a direction and a bracket for one market, at the caller's own barriers.
/// </summary>
/// <remarks>
/// <para>
/// This is the platform's second capability — "just give me a signal for this currency" — and it is
/// read-only in the strongest sense: <b>nothing here places, sizes, or authorizes an order</b>. A signal
/// is evidence, not authorization (<c>docs/LIVE_TRADING_SAFETY.md</c>), and order submission happens only
/// inside the bot scheduler, never inside an HTTP request. A request can be replayed by a browser refresh;
/// a trade must not be.
/// </para>
/// <para>
/// Routed at <c>/api/v1/ml/signals</c> rather than at <c>/api/v1/signal</c> so it sits alongside the
/// engine's other endpoints, while carrying its own <c>Signal.*</c> permissions — reading a signal and
/// inspecting the engine's configuration are different privileges.
/// </para>
/// </remarks>
[ApiVersion("1")]
[CustomAuthorize]
[ControllerInfo("Signal", "سیگنال")]
[Route("api/v{version:apiVersion}/ml/signals")]
public class SignalController(
    IMlServiceClient mlService,
    IMarketDataSourceResolver marketData,
    IOptions<TradingOptions> trading,
    IOptions<MarketDataOptions> marketDataOptions) : BaseController
{
    /// <summary>
    /// A directional signal with entry, take-profit and stop-loss prices for one market.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The caller sends the market and the bet; the API fetches the closed-candle window itself. Both
    /// barriers are percent of the entry price, both must be greater than zero, and both are inputs to
    /// the model rather than filters on its output — a 2% / 1% bet and a 1% / 2% bet on the same candle
    /// are two different questions and get two separately calibrated answers.
    /// </para>
    /// <para>
    /// The symbol is deliberately <em>not</em> checked against <c>Trading:Risk:AllowedSymbols</c>. That
    /// allowlist governs what may be traded, and this endpoint trades nothing; refusing to answer for a
    /// market outside it would remove the ability to research a market before enabling it, without
    /// preventing a single order.
    /// </para>
    /// </remarks>
    [HttpPost]
    [Permission(PermissionType.Get)]
    public async Task<ApiResult<SignalResponseDto>> GetSignal(
        [FromBody] SignalRequestDto request,
        CancellationToken ct)
    {
        if (request is null)
            throw new BadRequestException("بدنه درخواست الزامی است");

        var symbol = (request.Symbol ?? string.Empty).Trim().ToUpperInvariant();
        var interval = (request.Interval ?? string.Empty).Trim();

        if (symbol.Length == 0)
            throw new BadRequestException("نماد ارز الزامی است");

        if (interval.Length == 0)
            throw new BadRequestException("بازه زمانی کندل الزامی است");

        if (!CandleInterval.TryToTimeSpan(interval, out _))
            throw new BadRequestException($"بازه زمانی '{interval}' پشتیبانی نمی شود");

        // A barrier at the entry price is touched immediately, which makes the question unanswerable
        // rather than merely aggressive. Zero is refused instead of being coerced to a default: a
        // default barrier would answer a bet the caller never placed.
        if (request.TakeProfitPercent <= 0)
            throw new BadRequestException("درصد حد سود باید بزرگتر از صفر باشد");

        if (request.StopLossPercent <= 0)
            throw new BadRequestException("درصد حد ضرر باید بزرگتر از صفر باشد");

        if (request.MinimumConfidence is < 0 or > 1)
            throw new BadRequestException("حداقل اطمینان باید بین صفر و یک باشد");

        var venue = request.Venue ?? marketDataOptions.Value.SignalVenue;
        var windowSize = Math.Max(1, trading.Value.CandleWindowSize);

        IReadOnlyList<MarketCandleData> candles;

        try
        {
            candles = await marketData
                .Resolve(venue)
                .GetClosedCandlesAsync(symbol, interval, windowSize, ct);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            // The window is never padded, shortened, or fetched from a different venue. Answering from
            // an incomplete window would produce a signal whose features silently span the wrong
            // stretch of time, and answering from another venue's prices would produce one for a market
            // the caller did not ask about. Both are worse than an error.
            throw new ServiceUnavailableException(
                $"دریافت کندل های {symbol} {interval} از {venue} ناموفق بود: {exception.Message}");
        }

        var parameters = new MlTradeParameters(
            TakeProfitPercent: request.TakeProfitPercent,
            StopLossPercent: request.StopLossPercent,
            AllowShort: request.AllowShort,
            MaxHoldingPeriods: request.MaxHoldingPeriods,
            MinimumConfidence: request.MinimumConfidence);

        var engineRequest = new MlSignalRequest(
            Symbol: symbol,
            Interval: interval,
            Candles: candles
                .Select(candle => new MlCandle(
                    candle.OpenTime,
                    candle.Open,
                    candle.High,
                    candle.Low,
                    candle.Close,
                    candle.Volume))
                .ToList(),
            Parameters: parameters);

        try
        {
            var signal = await mlService.GetSignalAsync(engineRequest, ct);

            return Ok(Project(signal, request, symbol, interval, venue, candles.Count));
        }
        catch (MlServiceException exception) when (exception.ErrorCode == "InvalidArgument")
        {
            throw new BadRequestException(exception.Message);
        }
        catch (MlServiceException exception)
        {
            throw new ServiceUnavailableException(exception.Message);
        }
    }

    /// <summary>
    /// Flattens the engine's answer and echoes the request context back with it.
    /// </summary>
    /// <remarks>
    /// The request is echoed so a stored or forwarded response is self-describing: a confidence of 0.61
    /// means nothing without the barriers it was calibrated for, and a reader who has lost the request
    /// cannot recover them from the levels alone.
    /// </remarks>
    private static SignalResponseDto Project(
        MlSignal signal,
        SignalRequestDto request,
        string symbol,
        string interval,
        MarketVenue venue,
        int candleCount) => new()
    {
        Symbol = symbol,
        Interval = interval,
        Venue = venue,
        CandleCount = candleCount,
        TakeProfitPercent = request.TakeProfitPercent,
        StopLossPercent = request.StopLossPercent,
        AllowShort = request.AllowShort,
        Direction = signal.Direction switch
        {
            MlDirection.Long => TradeDirection.Long,
            MlDirection.Short => TradeDirection.Short,
            _ => TradeDirection.Flat,
        },
        Levels = signal.Levels is null
            ? null
            : new SignalLevelsDto(
                signal.Levels.EntryPrice,
                signal.Levels.TakeProfitPrice,
                signal.Levels.StopLossPrice,
                signal.Levels.Atr,
                signal.Levels.RiskRewardRatio,
                signal.Levels.TakeProfitAtr,
                signal.Levels.StopLossAtr),
        Confidence = signal.Confidence,
        LongConfidence = signal.LongConfidence,
        ShortConfidence = signal.ShortConfidence,
        Probabilities = new SignalProbabilitiesDto(
            signal.Probabilities.TakeProfitFirst,
            signal.Probabilities.StopLossFirst,
            signal.Probabilities.Timeout),
        ExpectedValue = signal.ExpectedValue,
        CandleOpenTime = signal.CandleOpenTime,
        ValidUntil = signal.ValidUntil,
        ModelId = signal.ModelId,
        ModelVersion = signal.ModelVersion,
        ModelTrainedAt = signal.ModelTrainedAt,
        UsedWildcardModel = signal.UsedWildcardModel,
        InputDigestSha256 = signal.InputDigestSha256,
        Rationale = signal.Rationale,
        Warning = signal.Warning,
        BarrierExtrapolated = signal.BarrierExtrapolated,
        ProcessingMilliseconds = signal.ProcessingMilliseconds,
    };
}
