using CryptoSignal.Api.Adapter.Persistence.Contexts;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;

namespace CryptoSignal.Api.Adapter.Repos.Implementations.Trading;

/// <summary>
/// Concrete repositories closing <see cref="Repo{T}"/> over the trading entities.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="Repo{T}"/> is abstract, and the Scrutor scan in <c>Program.cs</c> registers
/// <em>classes</em> assignable to <c>IRepo&lt;&gt;</c> — an abstract open generic is skipped. Without a
/// closed, non-abstract type per entity, <c>IRepo&lt;TradingBot&gt;</c> resolves to nothing and every
/// consumer of it fails at activation rather than at compile time. These one-line wrappers exist purely
/// to give the scan something to register, which is the same reason <c>AuthRepos.cs</c> exists.
/// </para>
/// <para>
/// No entity gets a bespoke repository interface. The trading layer asks questions of these tables
/// through <c>IRepo&lt;T&gt;.TableNoTracking</c> and specifications; adding a named interface per table
/// would be eleven abstractions carrying no behaviour.
/// </para>
/// </remarks>
public sealed class TradingBotRepo(CryptoSignalDbContext ctx) : Repo<TradingBot>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class BotRunRepo(CryptoSignalDbContext ctx) : Repo<BotRun>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class StrategyDecisionRepo(CryptoSignalDbContext ctx) : Repo<StrategyDecision>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class OrderIntentRepo(CryptoSignalDbContext ctx) : Repo<OrderIntent>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class RiskDecisionRepo(CryptoSignalDbContext ctx) : Repo<RiskDecision>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class ExchangeOrderRepo(CryptoSignalDbContext ctx) : Repo<ExchangeOrder>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class OrderFillRepo(CryptoSignalDbContext ctx) : Repo<OrderFill>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class BotPositionRepo(CryptoSignalDbContext ctx) : Repo<BotPosition>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class KillSwitchRepo(CryptoSignalDbContext ctx) : Repo<KillSwitch>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class BotAuditEventRepo(CryptoSignalDbContext ctx) : Repo<BotAuditEvent>(ctx);

/// <inheritdoc cref="TradingBotRepo"/>
public sealed class MarketCandleRepo(CryptoSignalDbContext ctx) : Repo<MarketCandle>(ctx);
