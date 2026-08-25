using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace CryptoSignal.Api.Migrations
{
    /// <inheritdoc />
    public partial class Trading : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "BotAuditEvents",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    BotId = table.Column<Guid>(type: "uuid", nullable: true),
                    OperatingMode = table.Column<int>(type: "integer", nullable: false),
                    EventType = table.Column<int>(type: "integer", nullable: false),
                    OccurredAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CorrelationId = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: false),
                    Sequence = table.Column<int>(type: "integer", nullable: false),
                    Summary = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false),
                    DetailJson = table.Column<string>(type: "jsonb", nullable: true),
                    StrategyDecisionId = table.Column<Guid>(type: "uuid", nullable: true),
                    OrderIntentId = table.Column<Guid>(type: "uuid", nullable: true),
                    RiskDecisionId = table.Column<Guid>(type: "uuid", nullable: true),
                    ExchangeOrderId = table.Column<Guid>(type: "uuid", nullable: true),
                    OrderFillId = table.Column<Guid>(type: "uuid", nullable: true),
                    BotPositionId = table.Column<Guid>(type: "uuid", nullable: true),
                    KillSwitchId = table.Column<Guid>(type: "uuid", nullable: true),
                    Symbol = table.Column<string>(type: "character varying(30)", unicode: false, maxLength: 30, nullable: true),
                    CandleOpenTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    ModelVersion = table.Column<string>(type: "character varying(128)", unicode: false, maxLength: 128, nullable: true),
                    ActorUserId = table.Column<Guid>(type: "uuid", nullable: true),
                    ActorUserName = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_BotAuditEvents", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "KillSwitches",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Scope = table.Column<int>(type: "integer", nullable: false),
                    ScopeOperatingMode = table.Column<int>(type: "integer", nullable: true),
                    ScopeVenue = table.Column<int>(type: "integer", nullable: true),
                    ScopeBotId = table.Column<Guid>(type: "uuid", nullable: true),
                    ScopeSymbol = table.Column<string>(type: "character varying(30)", unicode: false, maxLength: 30, nullable: true),
                    IsEngaged = table.Column<bool>(type: "boolean", nullable: false),
                    Reason = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false),
                    IsAutomatic = table.Column<bool>(type: "boolean", nullable: false),
                    TriggerDetail = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    EngagedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    EngagedByUserId = table.Column<Guid>(type: "uuid", nullable: true),
                    EngagedByUserName = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    DisengagedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    DisengagedByUserId = table.Column<Guid>(type: "uuid", nullable: true),
                    DisengagedByUserName = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_KillSwitches", x => x.Id);
                    table.CheckConstraint("CK_KillSwitches_ScopeTargetMatches", "(\n    (\"Scope\" = 1 AND \"ScopeOperatingMode\" IS NULL AND \"ScopeVenue\" IS NULL AND \"ScopeBotId\" IS NULL AND \"ScopeSymbol\" IS NULL)\n OR (\"Scope\" = 2 AND \"ScopeOperatingMode\" IS NOT NULL AND \"ScopeVenue\" IS NULL AND \"ScopeBotId\" IS NULL AND \"ScopeSymbol\" IS NULL)\n OR (\"Scope\" = 3 AND \"ScopeVenue\" IS NOT NULL AND \"ScopeOperatingMode\" IS NULL AND \"ScopeBotId\" IS NULL AND \"ScopeSymbol\" IS NULL)\n OR (\"Scope\" = 4 AND \"ScopeBotId\" IS NOT NULL AND \"ScopeOperatingMode\" IS NULL AND \"ScopeVenue\" IS NULL AND \"ScopeSymbol\" IS NULL)\n OR (\"Scope\" = 5 AND \"ScopeSymbol\" IS NOT NULL AND \"ScopeOperatingMode\" IS NULL AND \"ScopeVenue\" IS NULL AND \"ScopeBotId\" IS NULL)\n)");
                });

            migrationBuilder.CreateTable(
                name: "MarketCandles",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Venue = table.Column<int>(type: "integer", nullable: false),
                    Symbol = table.Column<string>(type: "character varying(30)", unicode: false, maxLength: 30, nullable: false),
                    Interval = table.Column<string>(type: "character varying(10)", unicode: false, maxLength: 10, nullable: false),
                    OpenTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CloseTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    Open = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    High = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    Low = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    Close = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    Volume = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    QuoteVolume = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    TradeCount = table.Column<int>(type: "integer", nullable: true),
                    IsClosed = table.Column<bool>(type: "boolean", nullable: false),
                    FetchedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MarketCandles", x => x.Id);
                    table.CheckConstraint("CK_MarketCandles_CloseTimeAfterOpenTime", "\"CloseTime\" > \"OpenTime\"");
                    table.CheckConstraint("CK_MarketCandles_HighNotBelowLow", "\"High\" >= \"Low\"");
                });

            migrationBuilder.CreateTable(
                name: "TradingBots",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(120)", maxLength: 120, nullable: false),
                    Description = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                    Symbol = table.Column<string>(type: "character varying(30)", unicode: false, maxLength: 30, nullable: false),
                    Interval = table.Column<string>(type: "character varying(10)", unicode: false, maxLength: 10, nullable: false),
                    Venue = table.Column<int>(type: "integer", nullable: false),
                    OperatingMode = table.Column<int>(type: "integer", nullable: false),
                    TakeProfitPercent = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    StopLossPercent = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    AllowShort = table.Column<bool>(type: "boolean", nullable: false),
                    QuoteNotionalPerTrade = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    MinimumConfidence = table.Column<double>(type: "double precision", nullable: false),
                    MaxHoldingPeriods = table.Column<int>(type: "integer", nullable: false),
                    CadenceSeconds = table.Column<int>(type: "integer", nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    StatusReason = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                    FaultedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastEvaluatedCandleOpenTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastTickAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    MaxOrderNotional = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    MaxPositionNotional = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    MaxDailyLoss = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    MaxDrawdown = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    MaxConcurrentPositions = table.Column<int>(type: "integer", nullable: false),
                    MaxOrdersPerDay = table.Column<int>(type: "integer", nullable: false),
                    MaxConsecutiveFailures = table.Column<int>(type: "integer", nullable: false),
                    MaxSlippageBps = table.Column<int>(type: "integer", nullable: false),
                    ExpectedModelVersion = table.Column<string>(type: "character varying(128)", unicode: false, maxLength: 128, nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_TradingBots", x => x.Id);
                    table.CheckConstraint("CK_TradingBots_CadenceSeconds_Positive", "\"CadenceSeconds\" > 0");
                    table.CheckConstraint("CK_TradingBots_QuoteNotionalPerTrade_Positive", "\"QuoteNotionalPerTrade\" > 0");
                    table.CheckConstraint("CK_TradingBots_StopLossPercent_Positive", "\"StopLossPercent\" > 0");
                    table.CheckConstraint("CK_TradingBots_TakeProfitPercent_Positive", "\"TakeProfitPercent\" > 0");
                });

            migrationBuilder.CreateTable(
                name: "BotPositions",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    BotId = table.Column<Guid>(type: "uuid", nullable: false),
                    OperatingMode = table.Column<int>(type: "integer", nullable: false),
                    Venue = table.Column<int>(type: "integer", nullable: false),
                    Symbol = table.Column<string>(type: "character varying(30)", unicode: false, maxLength: 30, nullable: false),
                    Direction = table.Column<int>(type: "integer", nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    AverageEntryPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    Quantity = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    EntryNotional = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    TakeProfitPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    StopLossPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    OpenedByOrderIntentId = table.Column<Guid>(type: "uuid", nullable: true),
                    ClosedByOrderIntentId = table.Column<Guid>(type: "uuid", nullable: true),
                    OpenedFromCandleOpenTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    OpenedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ClosedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    BarsHeld = table.Column<int>(type: "integer", nullable: false),
                    AverageExitPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    CloseReason = table.Column<int>(type: "integer", nullable: true),
                    RealizedPnl = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    FeesPaid = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    UnrealizedPnl = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    LastMarkPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    LastMarkedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    MaxAdverseExcursion = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_BotPositions", x => x.Id);
                    table.CheckConstraint("CK_BotPositions_Quantity_Positive", "\"Quantity\" > 0");
                    table.ForeignKey(
                        name: "FK_BotPositions_TradingBots_BotId",
                        column: x => x.BotId,
                        principalTable: "TradingBots",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "BotRuns",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    BotId = table.Column<Guid>(type: "uuid", nullable: false),
                    OperatingMode = table.Column<int>(type: "integer", nullable: false),
                    LeaseOwner = table.Column<string>(type: "character varying(128)", unicode: false, maxLength: 128, nullable: false),
                    StartedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    LastHeartbeatAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    EndedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    TickCount = table.Column<long>(type: "bigint", nullable: false),
                    DecisionCount = table.Column<long>(type: "bigint", nullable: false),
                    OrderCount = table.Column<long>(type: "bigint", nullable: false),
                    ErrorCount = table.Column<long>(type: "bigint", nullable: false),
                    ConsecutiveFailureCount = table.Column<int>(type: "integer", nullable: false),
                    LastError = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    LastErrorAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastTickAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_BotRuns", x => x.Id);
                    table.ForeignKey(
                        name: "FK_BotRuns_TradingBots_BotId",
                        column: x => x.BotId,
                        principalTable: "TradingBots",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "StrategyDecisions",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    BotId = table.Column<Guid>(type: "uuid", nullable: false),
                    BotRunId = table.Column<Guid>(type: "uuid", nullable: true),
                    OperatingMode = table.Column<int>(type: "integer", nullable: false),
                    Symbol = table.Column<string>(type: "character varying(30)", unicode: false, maxLength: 30, nullable: false),
                    Interval = table.Column<string>(type: "character varying(10)", unicode: false, maxLength: 10, nullable: false),
                    CandleOpenTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CandleWindowDigest = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: false),
                    Action = table.Column<int>(type: "integer", nullable: false),
                    Direction = table.Column<int>(type: "integer", nullable: false),
                    ReasonCode = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: false),
                    Confidence = table.Column<double>(type: "double precision", nullable: false),
                    LongConfidence = table.Column<double>(type: "double precision", nullable: false),
                    ShortConfidence = table.Column<double>(type: "double precision", nullable: false),
                    ExpectedValue = table.Column<double>(type: "double precision", nullable: false),
                    ProbabilityTakeProfitFirst = table.Column<double>(type: "double precision", nullable: false),
                    ProbabilityStopLossFirst = table.Column<double>(type: "double precision", nullable: false),
                    ProbabilityTimeout = table.Column<double>(type: "double precision", nullable: false),
                    EntryPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    TakeProfitPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    StopLossPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    Atr = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    RiskRewardRatio = table.Column<double>(type: "double precision", nullable: true),
                    TakeProfitAtr = table.Column<double>(type: "double precision", nullable: true),
                    StopLossAtr = table.Column<double>(type: "double precision", nullable: true),
                    ModelId = table.Column<string>(type: "character varying(128)", unicode: false, maxLength: 128, nullable: false),
                    ModelVersion = table.Column<string>(type: "character varying(128)", unicode: false, maxLength: 128, nullable: false),
                    ModelTrainedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    UsedWildcardModel = table.Column<bool>(type: "boolean", nullable: false),
                    BarrierExtrapolated = table.Column<bool>(type: "boolean", nullable: false),
                    Warning = table.Column<string>(type: "character varying(1000)", maxLength: 1000, nullable: true),
                    ValidUntil = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    EngineRequestId = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: true),
                    ProcessingMilliseconds = table.Column<double>(type: "double precision", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_StrategyDecisions", x => x.Id);
                    table.ForeignKey(
                        name: "FK_StrategyDecisions_BotRuns_BotRunId",
                        column: x => x.BotRunId,
                        principalTable: "BotRuns",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_StrategyDecisions_TradingBots_BotId",
                        column: x => x.BotId,
                        principalTable: "TradingBots",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "OrderIntents",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    StrategyDecisionId = table.Column<Guid>(type: "uuid", nullable: false),
                    BotId = table.Column<Guid>(type: "uuid", nullable: false),
                    OperatingMode = table.Column<int>(type: "integer", nullable: false),
                    ClientOrderId = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: false),
                    Symbol = table.Column<string>(type: "character varying(30)", unicode: false, maxLength: 30, nullable: false),
                    Direction = table.Column<int>(type: "integer", nullable: false),
                    Side = table.Column<int>(type: "integer", nullable: false),
                    Type = table.Column<int>(type: "integer", nullable: false),
                    Quantity = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    LimitPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    TakeProfitPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    StopLossPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    TimeInForce = table.Column<int>(type: "integer", nullable: true),
                    ReferencePrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    EstimatedNotional = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    StatusReason = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                    SubmittedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CompletedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_OrderIntents", x => x.Id);
                    table.CheckConstraint("CK_OrderIntents_Quantity_Positive", "\"Quantity\" > 0");
                    table.ForeignKey(
                        name: "FK_OrderIntents_StrategyDecisions_StrategyDecisionId",
                        column: x => x.StrategyDecisionId,
                        principalTable: "StrategyDecisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_OrderIntents_TradingBots_BotId",
                        column: x => x.BotId,
                        principalTable: "TradingBots",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "ExchangeOrders",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    OrderIntentId = table.Column<Guid>(type: "uuid", nullable: false),
                    BotId = table.Column<Guid>(type: "uuid", nullable: false),
                    OperatingMode = table.Column<int>(type: "integer", nullable: false),
                    Venue = table.Column<int>(type: "integer", nullable: false),
                    VenueOrderId = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: true),
                    ClientOrderId = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    FilledQuantity = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    AverageFillPrice = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: true),
                    RequestHash = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: true),
                    ResponseHash = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: true),
                    SubmittedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    VenueUpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastReconciledAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ExchangeOrders", x => x.Id);
                    table.ForeignKey(
                        name: "FK_ExchangeOrders_OrderIntents_OrderIntentId",
                        column: x => x.OrderIntentId,
                        principalTable: "OrderIntents",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "RiskDecisions",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    OrderIntentId = table.Column<Guid>(type: "uuid", nullable: false),
                    BotId = table.Column<Guid>(type: "uuid", nullable: false),
                    Allowed = table.Column<bool>(type: "boolean", nullable: false),
                    FailedChecksCsv = table.Column<string>(type: "character varying(1000)", unicode: false, maxLength: 1000, nullable: false),
                    Detail = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    SnapshotJson = table.Column<string>(type: "jsonb", nullable: true),
                    EvaluatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RiskDecisions", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RiskDecisions_OrderIntents_OrderIntentId",
                        column: x => x.OrderIntentId,
                        principalTable: "OrderIntents",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "OrderFills",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    ExchangeOrderId = table.Column<Guid>(type: "uuid", nullable: false),
                    BotId = table.Column<Guid>(type: "uuid", nullable: false),
                    OperatingMode = table.Column<int>(type: "integer", nullable: false),
                    Venue = table.Column<int>(type: "integer", nullable: false),
                    VenueTradeId = table.Column<string>(type: "character varying(64)", unicode: false, maxLength: 64, nullable: false),
                    Price = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    Quantity = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    Fee = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    FeeAsset = table.Column<string>(type: "character varying(20)", unicode: false, maxLength: 20, nullable: false),
                    IsMaker = table.Column<bool>(type: "boolean", nullable: true),
                    ExecutedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_OrderFills", x => x.Id);
                    table.ForeignKey(
                        name: "FK_OrderFills_ExchangeOrders_ExchangeOrderId",
                        column: x => x.ExchangeOrderId,
                        principalTable: "ExchangeOrders",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_BotAuditEvents_BotId_OccurredAt",
                table: "BotAuditEvents",
                columns: new[] { "BotId", "OccurredAt" });

            migrationBuilder.CreateIndex(
                name: "IX_BotAuditEvents_EventType_OccurredAt",
                table: "BotAuditEvents",
                columns: new[] { "EventType", "OccurredAt" });

            migrationBuilder.CreateIndex(
                name: "UX_BotAuditEvents_CorrelationId_Sequence",
                table: "BotAuditEvents",
                columns: new[] { "CorrelationId", "Sequence" },
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_BotPositions_BotId_OpenedAt",
                table: "BotPositions",
                columns: new[] { "BotId", "OpenedAt" });

            migrationBuilder.CreateIndex(
                name: "UX_BotPositions_BotId_OperatingMode_Open",
                table: "BotPositions",
                columns: new[] { "BotId", "OperatingMode" },
                unique: true,
                filter: "\"Status\" = 1 AND \"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_BotRuns_BotId_StartedAt",
                table: "BotRuns",
                columns: new[] { "BotId", "StartedAt" });

            migrationBuilder.CreateIndex(
                name: "UX_BotRuns_BotId_Open",
                table: "BotRuns",
                column: "BotId",
                unique: true,
                filter: "\"EndedAt\" IS NULL AND \"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_ExchangeOrders_ClientOrderId",
                table: "ExchangeOrders",
                column: "ClientOrderId");

            migrationBuilder.CreateIndex(
                name: "IX_ExchangeOrders_OrderIntentId",
                table: "ExchangeOrders",
                column: "OrderIntentId");

            migrationBuilder.CreateIndex(
                name: "UX_ExchangeOrders_Venue_VenueOrderId",
                table: "ExchangeOrders",
                columns: new[] { "Venue", "VenueOrderId" },
                unique: true,
                filter: "\"VenueOrderId\" IS NOT NULL AND \"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "UX_KillSwitches_Scope_Engaged",
                table: "KillSwitches",
                columns: new[] { "Scope", "ScopeOperatingMode", "ScopeVenue", "ScopeBotId", "ScopeSymbol" },
                unique: true,
                filter: "\"IsEngaged\" = true AND \"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "UX_MarketCandles_Venue_Symbol_Interval_OpenTime",
                table: "MarketCandles",
                columns: new[] { "Venue", "Symbol", "Interval", "OpenTime" },
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_OrderFills_ExchangeOrderId",
                table: "OrderFills",
                column: "ExchangeOrderId");

            migrationBuilder.CreateIndex(
                name: "UX_OrderFills_Venue_VenueTradeId",
                table: "OrderFills",
                columns: new[] { "Venue", "VenueTradeId" },
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_OrderIntents_BotId_Status",
                table: "OrderIntents",
                columns: new[] { "BotId", "Status" });

            migrationBuilder.CreateIndex(
                name: "UX_OrderIntents_ClientOrderId",
                table: "OrderIntents",
                column: "ClientOrderId",
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "UX_OrderIntents_StrategyDecisionId",
                table: "OrderIntents",
                column: "StrategyDecisionId",
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "UX_RiskDecisions_OrderIntentId",
                table: "RiskDecisions",
                column: "OrderIntentId",
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_StrategyDecisions_BotRunId",
                table: "StrategyDecisions",
                column: "BotRunId");

            migrationBuilder.CreateIndex(
                name: "UX_StrategyDecisions_BotId_CandleOpenTime",
                table: "StrategyDecisions",
                columns: new[] { "BotId", "CandleOpenTime" },
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_TradingBots_Mode_Symbol_Interval",
                table: "TradingBots",
                columns: new[] { "OperatingMode", "Symbol", "Interval" });

            migrationBuilder.CreateIndex(
                name: "IX_TradingBots_Status",
                table: "TradingBots",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "UX_TradingBots_Name_Active",
                table: "TradingBots",
                column: "Name",
                unique: true,
                filter: "\"IsDeleted\" = false");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "BotAuditEvents");

            migrationBuilder.DropTable(
                name: "BotPositions");

            migrationBuilder.DropTable(
                name: "KillSwitches");

            migrationBuilder.DropTable(
                name: "MarketCandles");

            migrationBuilder.DropTable(
                name: "OrderFills");

            migrationBuilder.DropTable(
                name: "RiskDecisions");

            migrationBuilder.DropTable(
                name: "ExchangeOrders");

            migrationBuilder.DropTable(
                name: "OrderIntents");

            migrationBuilder.DropTable(
                name: "StrategyDecisions");

            migrationBuilder.DropTable(
                name: "BotRuns");

            migrationBuilder.DropTable(
                name: "TradingBots");
        }
    }
}
