using CryptoSignal.Contracts.Ml.V1;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Api.Application.Options;
using Google.Protobuf.WellKnownTypes;
using Grpc.Core;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.Clients;

/// <summary>
/// Translates between the .NET contract types and the generated gRPC messages, and nowhere else in
/// the codebase does that translation happen.
/// </summary>
/// <remarks>
/// <para>
/// Two rules govern every line here, both inherited from the proto's own header:
/// </para>
/// <para>
/// <b>Prices cross as decimal strings.</b> A price never becomes a <c>double</c> on this boundary —
/// it is read straight into <see cref="decimal"/> by <see cref="MlWire.Money(string, string)"/> and
/// written back by <see cref="MlWire.Money(decimal)"/>. The audit chain depends on the stored price
/// being byte-for-byte the price the engine computed.
/// </para>
/// <para>
/// <b>An unset message is not a zeroed message.</b> proto3 gives an absent submessage or timestamp
/// the same reading as one full of zeros, so every message-typed field is null-checked before it is
/// read. An absent <c>ModelTrainedAt</c> is "not known", which is a different fact from 1970-01-01,
/// and an absent <c>Levels</c> (a HOLD carries none) must stay null rather than become a bracket of
/// zeros.
/// </para>
/// </remarks>
public sealed class MlServiceClient(
    MlEngineService.MlEngineServiceClient client,
    IOptions<MlServiceOptions> options,
    ILogger<MlServiceClient> logger)
    : IMlServiceClient
{
    public async Task<DependencyHealth> GetHealthAsync(CancellationToken cancellationToken)
    {
        try
        {
            var response = await client.GetCapabilitiesAsync(
                new GetCapabilitiesRequest { RequestId = Guid.NewGuid().ToString() },
                deadline: Deadline(),
                cancellationToken: cancellationToken);
            return new DependencyHealth(
                "python-ml",
                response.ModelReady ? "healthy" : "unhealthy",
                response.ModelReady
                    ? $"mode={response.OperatingMode}, markets={response.SupportedMarkets.Count}"
                    : "no model loaded");
        }
        catch (RpcException exception)
        {
            logger.LogWarning(exception, "Python ML gRPC health check failed");
            return new DependencyHealth(
                "python-ml",
                "unavailable",
                $"gRPC {exception.StatusCode}: {exception.Status.Detail}");
        }
    }

    public async Task<MlServiceCapabilities?> GetCapabilitiesAsync(CancellationToken cancellationToken)
    {
        try
        {
            var response = await client.GetCapabilitiesAsync(
                new GetCapabilitiesRequest { RequestId = Guid.NewGuid().ToString() },
                deadline: Deadline(),
                cancellationToken: cancellationToken);
            return new MlServiceCapabilities(
                response.Service,
                response.ServiceVersion,
                response.ProtocolVersion,
                response.Capabilities.ToArray(),
                response.SupportedOperations.ToArray(),
                response.ModelReady,
                response.MinimumCandles,
                response.MaximumCandles,
                response.SupportedMarkets
                    .Select(m => new MlSupportedMarket(
                        m.Symbol, m.Interval, m.ModelId, m.ModelVersion, m.IsWildcard))
                    .ToArray(),
                response.WildcardModelReady,
                response.OperatingMode);
        }
        catch (RpcException exception)
        {
            logger.LogWarning(exception, "Python ML gRPC capability request failed");
            return null;
        }
    }

    public async Task<MlModelInfo?> GetModelInfoAsync(
        string symbol,
        string interval,
        CancellationToken cancellationToken)
    {
        try
        {
            var response = await client.GetModelInfoAsync(
                new GetModelInfoRequest
                {
                    RequestId = Guid.NewGuid().ToString(),
                    // The engine rejects an unknown interval outright, and an omitted query
                    // parameter means "the default market" rather than "nothing" — resolve that
                    // to the platform's working interval instead of failing the request.
                    Symbol = string.IsNullOrWhiteSpace(symbol) ? "BTCUSDT" : symbol,
                    Interval = string.IsNullOrWhiteSpace(interval) ? "1h" : interval,
                },
                deadline: Deadline(),
                cancellationToken: cancellationToken);
            return new MlModelInfo(
                response.Ready,
                response.ModelId,
                response.ModelVersion,
                response.ProjectVersion,
                response.Symbol,
                response.Interval,
                OptionalTime(response.TrainedAt),
                response.FeatureCount,
                response.IsWildcard,
                response.LabelScheme,
                response.CalibrationMethod,
                response.DefaultMaxHoldingPeriods,
                response.MinimumBarrierAtr,
                response.MaximumBarrierAtr,
                response.ConfidenceCeiling,
                response.ConfidenceReach
                    .Select(r => new MlConfidenceReach(r.Threshold, r.Share))
                    .ToArray());
        }
        catch (RpcException exception)
        {
            logger.LogWarning(exception, "Python ML gRPC model-info request failed");
            return null;
        }
    }

    public async Task<MlSignal> GetSignalAsync(
        MlSignalRequest request,
        CancellationToken cancellationToken)
    {
        var grpcRequest = new GetSignalRequest
        {
            RequestId = RequestId(request.RequestId),
            Symbol = request.Symbol,
            Interval = request.Interval,
            Parameters = ToProto(request.Parameters),
            ExpectedModelVersion = request.ExpectedModelVersion ?? string.Empty,
        };
        grpcRequest.Candles.AddRange(request.Candles.Select(ToProto));

        try
        {
            var response = await client.GetSignalAsync(
                grpcRequest, deadline: Deadline(), cancellationToken: cancellationToken);
            return new MlSignal(
                response.RequestId,
                (MlDirection)(int)response.Direction,
                OptionalLevels(response.Levels),
                response.Confidence,
                Probabilities(response.Probabilities),
                response.ExpectedValue,
                response.LongConfidence,
                response.ShortConfidence,
                response.Symbol,
                response.Interval,
                OptionalTime(response.CandleOpenTime),
                OptionalTime(response.ValidUntil),
                response.ModelId,
                response.ModelVersion,
                OptionalTime(response.ModelTrainedAt),
                response.UsedWildcardModel,
                response.InputDigestSha256,
                response.Rationale.ToArray(),
                response.Warning,
                response.ProcessingMilliseconds,
                response.BarrierExtrapolated);
        }
        catch (RpcException exception)
        {
            throw Translate(exception, "signal");
        }
    }

    public async Task<MlBotDecision> EvaluateBotDecisionAsync(
        MlBotDecisionRequest request,
        CancellationToken cancellationToken)
    {
        var grpcRequest = new EvaluateBotDecisionRequest
        {
            RequestId = RequestId(request.RequestId),
            BotId = request.BotId ?? string.Empty,
            Symbol = request.Symbol,
            Interval = request.Interval,
            Parameters = ToProto(request.Parameters),
            ExpectedModelVersion = request.ExpectedModelVersion ?? string.Empty,
        };
        grpcRequest.Candles.AddRange(request.Candles.Select(ToProto));

        // Left unset when the bot is flat. A zeroed OpenPosition is a valid protobuf message that the
        // engine would read as a position of zero size — a flat bot being told it holds something.
        if (request.Position is { } position)
        {
            grpcRequest.Position = ToProto(position);
        }

        // Multi-timeframe context: higher-TF candles the engine merges in as confluence features.
        // Omitted when not configured, so existing bots are unaffected.
        if (request.ContextCandles is not null && request.ContextInterval is not null)
        {
            grpcRequest.ContextInterval = request.ContextInterval;
            grpcRequest.ContextCandles.AddRange(request.ContextCandles.Select(ToProto));
        }

        try
        {
            var response = await client.EvaluateBotDecisionAsync(
                grpcRequest, deadline: Deadline(), cancellationToken: cancellationToken);
            return new MlBotDecision(
                response.RequestId,
                (MlBotAction)(int)response.Action,
                (MlDirection)(int)response.Direction,
                OptionalLevels(response.Levels),
                response.Confidence,
                Probabilities(response.Probabilities),
                response.ExpectedValue,
                response.ReasonCode,
                response.Rationale.ToArray(),
                response.Symbol,
                response.Interval,
                OptionalTime(response.CandleOpenTime),
                OptionalTime(response.ValidUntil),
                response.ModelId,
                response.ModelVersion,
                OptionalTime(response.ModelTrainedAt),
                response.UsedWildcardModel,
                response.InputDigestSha256,
                response.Warning,
                response.ProcessingMilliseconds,
                response.BarrierExtrapolated);
        }
        catch (RpcException exception)
        {
            throw Translate(exception, "bot decision");
        }
    }

    /// <inheritdoc/>
    public async Task<MlTradeOutcomeAck?> RecordTradeOutcomeAsync(
        MlTradeOutcome outcome,
        CancellationToken cancellationToken)
    {
        var grpcRequest = new RecordTradeOutcomeRequest
        {
            RequestId = RequestId(outcome.RequestId),
            BotId = outcome.BotId,
            Symbol = outcome.Symbol,
            Interval = outcome.Interval,
            ModelId = outcome.ModelId ?? string.Empty,
            ModelVersion = outcome.ModelVersion ?? string.Empty,
            Direction = (TradeDirection)(int)outcome.Direction,
            TakeProfitPercent = MlWire.Money(outcome.TakeProfitPercent),
            StopLossPercent = MlWire.Money(outcome.StopLossPercent),
            CloseReason = outcome.CloseReason,
            RealizedPnl = MlWire.Money(outcome.RealizedPnl),
            BarsHeld = outcome.BarsHeld,
            DecisionCandleOpenTime = Timestamp.FromDateTimeOffset(outcome.DecisionCandleOpenTime),
            ClosedAt = Timestamp.FromDateTimeOffset(outcome.ClosedAt),
        };
        grpcRequest.Candles.AddRange(outcome.Candles.Select(ToProto));

        try
        {
            var response = await client.RecordTradeOutcomeAsync(
                grpcRequest, deadline: Deadline(), cancellationToken: cancellationToken);
            return new MlTradeOutcomeAck(
                response.RequestId,
                response.Status,
                response.SamplesStored,
                response.TrainingTriggered);
        }
        catch (RpcException exception)
        {
            // Best-effort by contract: a lost sample is a lost training datum, never a trading fault.
            // Logged and swallowed so a position close can never fail because the sample store did.
            logger.LogWarning(
                exception,
                "RecordTradeOutcome failed with {StatusCode} — sample not stored",
                exception.StatusCode);
            return null;
        }
    }

    /// <inheritdoc/>
    public async Task<MlTrainingStatus?> GetTrainingStatusAsync(
        CancellationToken cancellationToken)
    {
        try
        {
            var response = await client.GetTrainingStatusAsync(
                new GetTrainingStatusRequest { RequestId = Guid.NewGuid().ToString() },
                deadline: Deadline(),
                cancellationToken: cancellationToken);
            return new MlTrainingStatus(
                response.RequestId,
                response.OnlineLearningEnabled,
                response.Markets
                    .Select(m => new MlMarketTrainingStatus(
                        m.Symbol,
                        m.Interval,
                        m.SamplesStored,
                        m.SamplesSinceTraining,
                        string.IsNullOrEmpty(m.LastTrainedAt) ? null : m.LastTrainedAt,
                        string.IsNullOrEmpty(m.LastChallengerVersion) ? null : m.LastChallengerVersion,
                        m.LastVerdict,
                        m.LastVerdictReason,
                        m.TrainingInProgress))
                    .ToArray());
        }
        catch (RpcException exception)
        {
            logger.LogWarning(
                exception,
                "GetTrainingStatus failed with {StatusCode}",
                exception.StatusCode);
            return null;
        }
    }

    // ── outbound ────────────────────────────────────────────────────────────────

    private static Candle ToProto(MlCandle candle) => new()
    {
        OpenTime = Timestamp.FromDateTimeOffset(candle.OpenTime),
        Open = MlWire.Money(candle.Open),
        High = MlWire.Money(candle.High),
        Low = MlWire.Money(candle.Low),
        Close = MlWire.Money(candle.Close),
        Volume = MlWire.Money(candle.Volume),
    };

    private static TradeParameters ToProto(MlTradeParameters parameters) => new()
    {
        TakeProfitPercent = MlWire.Money(parameters.TakeProfitPercent),
        StopLossPercent = MlWire.Money(parameters.StopLossPercent),
        AllowShort = parameters.AllowShort,
        MaxHoldingPeriods = parameters.MaxHoldingPeriods,
        MinimumConfidence = parameters.MinimumConfidence,
    };

    private static OpenPosition ToProto(MlOpenPosition position)
    {
        var message = new OpenPosition
        {
            Direction = (TradeDirection)(int)position.Direction,
            EntryPrice = MlWire.Money(position.EntryPrice),
            Quantity = MlWire.Money(position.Quantity),
            BarsHeld = position.BarsHeld,
            // Empty string is the wire's "not supplied"; the engine falls back to the configured
            // percentage for whichever half of the bracket is absent.
            TakeProfitPrice = position.TakeProfitPrice is { } tp ? MlWire.Money(tp) : string.Empty,
            StopLossPrice = position.StopLossPrice is { } sl ? MlWire.Money(sl) : string.Empty,
        };
        if (position.OpenedAt is { } openedAt)
        {
            message.OpenedAt = Timestamp.FromDateTimeOffset(openedAt);
        }

        return message;
    }

    // ── inbound ─────────────────────────────────────────────────────────────────

    /// <summary>A timestamp, or null when the submessage is unset — never the epoch.</summary>
    private static DateTimeOffset? OptionalTime(Timestamp? value) =>
        value is null ? null : value.ToDateTimeOffset();

    /// <summary>Levels, or null when the response carries none (a HOLD does not).</summary>
    private static MlTradeLevels? OptionalLevels(TradeLevels? levels) =>
        levels is null
            ? null
            : new MlTradeLevels(
                MlWire.Money(levels.EntryPrice, "levels.entry_price"),
                MlWire.Money(levels.TakeProfitPrice, "levels.take_profit_price"),
                MlWire.Money(levels.StopLossPrice, "levels.stop_loss_price"),
                MlWire.Money(levels.Atr, "levels.atr"),
                levels.RiskRewardRatio,
                levels.TakeProfitAtr,
                levels.StopLossAtr);

    private static MlBarrierProbabilities Probabilities(BarrierProbabilities? probabilities) =>
        probabilities is null
            ? new MlBarrierProbabilities(0, 0, 0)
            : new MlBarrierProbabilities(
                probabilities.TakeProfitFirst,
                probabilities.StopLossFirst,
                probabilities.Timeout);

    private static string RequestId(string? requestId) =>
        string.IsNullOrWhiteSpace(requestId) ? Guid.NewGuid().ToString() : requestId;

    private MlServiceException Translate(RpcException exception, string operation)
    {
        logger.LogWarning(
            exception,
            "Python ML gRPC {Operation} failed with {StatusCode}",
            operation,
            exception.StatusCode);
        return new MlServiceException(
            exception.StatusCode.ToString(),
            exception.Status.Detail,
            exception);
    }

    private DateTime Deadline() => DateTime.UtcNow.AddSeconds(options.Value.DeadlineSeconds);
}
