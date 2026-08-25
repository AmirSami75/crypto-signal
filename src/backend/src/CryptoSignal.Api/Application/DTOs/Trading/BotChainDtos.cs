using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.DTOs.Trading;

/// <summary>
/// One recorded evaluation: what the engine was asked, what it answered, and against which model.
/// </summary>
/// <remarks>
/// Kept whether or not it led to an order. A HOLD is as much a decision as an OPEN, and a decision
/// history with the quiet ticks removed cannot answer "why did the bot not trade that move".
/// </remarks>
public sealed record BotDecisionDto(
    Guid Id,
    Guid BotId,
    OperatingMode OperatingMode,
    string Symbol,
    string Interval,
    DateTime CandleOpenTime,
    string CandleWindowDigest,
    BotDecisionAction Action,
    TradeDirection Direction,
    string ReasonCode,
    double Confidence,
    double LongConfidence,
    double ShortConfidence,
    double ExpectedValue,
    double ProbabilityTakeProfitFirst,
    double ProbabilityStopLossFirst,
    double ProbabilityTimeout,
    decimal? EntryPrice,
    decimal? TakeProfitPrice,
    decimal? StopLossPrice,
    decimal? Atr,
    double? RiskRewardRatio,
    string ModelId,
    string ModelVersion,
    DateTime? ModelTrainedAt,
    bool UsedWildcardModel,
    bool BarrierExtrapolated,
    string? Warning,
    DateTime? ValidUntil,
    double ProcessingMilliseconds,
    DateTime CreatedAt);

/// <summary>
/// The risk engine's verdict on one intent, kept whether it allowed or denied.
/// </summary>
/// <remarks>
/// A refusal is evidence, not an error to be discarded. <see cref="FailedChecks"/> names the checks that
/// failed and <see cref="SnapshotJson"/> is the limit set they ran against, so a denial can be explained
/// months later without re-deriving what the configuration was at the time.
/// </remarks>
public sealed record RiskDecisionDto(
    Guid Id,
    bool Allowed,
    IReadOnlyList<string> FailedChecks,
    string? Detail,
    string? SnapshotJson,
    DateTime EvaluatedAt);

/// <summary>One fill. Fees are in <see cref="FeeAsset"/>, which is not always the quote currency.</summary>
public sealed record OrderFillDto(
    Guid Id,
    MarketVenue Venue,
    string VenueTradeId,
    decimal Price,
    decimal Quantity,
    decimal Fee,
    string FeeAsset,
    bool? IsMaker,
    DateTime ExecutedAt);

/// <summary>
/// A submission to a venue, and what came back.
/// </summary>
/// <remarks>
/// <see cref="RequestHash"/> covers the unsigned request only. The signature is deliberately not stored:
/// it is a replayable credential artefact, and an audit trail is not a place to keep one.
/// </remarks>
public sealed record ExchangeOrderDto(
    Guid Id,
    MarketVenue Venue,
    string? VenueOrderId,
    string ClientOrderId,
    ExchangeOrderStatus Status,
    decimal FilledQuantity,
    decimal? AverageFillPrice,
    string? RequestHash,
    string? ResponseHash,
    DateTime SubmittedAt,
    DateTime? VenueUpdatedAt,
    DateTime? LastReconciledAt,
    IReadOnlyList<OrderFillDto> Fills);

/// <summary>
/// One intent and everything downstream of it: the risk verdict, the venue order, the fills.
/// </summary>
/// <remarks>
/// <see cref="ClientOrderId"/> is derived deterministically from the decision, which is what makes a
/// retried tick idempotent: the same decision produces the same id, and the venue rejects the duplicate
/// instead of opening a second position.
/// </remarks>
public sealed record OrderIntentDto(
    Guid Id,
    Guid BotId,
    Guid StrategyDecisionId,
    OperatingMode OperatingMode,
    string ClientOrderId,
    string Symbol,
    TradeDirection Direction,
    OrderSide Side,
    OrderType Type,
    decimal Quantity,
    decimal? LimitPrice,
    decimal? TakeProfitPrice,
    decimal? StopLossPrice,
    TimeInForce? TimeInForce,
    decimal ReferencePrice,
    decimal EstimatedNotional,
    OrderIntentStatus Status,
    string? StatusReason,
    DateTime? SubmittedAt,
    DateTime? CompletedAt,
    DateTime CreatedAt,
    RiskDecisionDto? RiskDecision,
    IReadOnlyList<ExchangeOrderDto> ExchangeOrders);

/// <summary>
/// One link in the audit chain: candle → model → decision → intent → risk → order → fill → position.
/// </summary>
/// <remarks>
/// <see cref="CorrelationId"/> plus <see cref="Sequence"/> is what makes the chain a chain: every event a
/// single tick produced shares the correlation id, and the sequence orders them within it. Ordering by
/// timestamp alone is not enough — several events of one tick land in the same millisecond.
/// </remarks>
public sealed record BotAuditEventDto(
    Guid Id,
    Guid? BotId,
    OperatingMode OperatingMode,
    BotAuditEventType EventType,
    string CorrelationId,
    int Sequence,
    string Summary,
    string? DetailJson,
    string? Symbol,
    DateTime? CandleOpenTime,
    string? ModelVersion,
    Guid? StrategyDecisionId,
    Guid? OrderIntentId,
    Guid? RiskDecisionId,
    Guid? ExchangeOrderId,
    Guid? OrderFillId,
    Guid? BotPositionId,
    Guid? KillSwitchId,
    string? ActorUserName,
    DateTime OccurredAt);
