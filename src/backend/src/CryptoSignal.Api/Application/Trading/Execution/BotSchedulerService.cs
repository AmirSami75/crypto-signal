using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.Application.Trading.Execution;

/// <summary>
/// The only thing in the platform that places orders: a background loop that wakes on a timer, finds the
/// bots whose cadence is due, and runs each one through <see cref="BotTickExecutor"/>.
/// </summary>
/// <remarks>
/// <para>
/// Order submission lives here and nowhere else — <c>docs/LIVE_TRADING_SAFETY.md</c> forbids it inside an
/// HTTP request, because a request can be replayed, cancelled halfway, or fired by a browser refresh, and
/// none of those may become a trade. The HTTP surface mutates bot <em>configuration</em>; this loop acts on it.
/// </para>
/// <para>
/// It is disabled by default (<see cref="TradingOptions.SchedulerEnabled"/>). A deployment that never sets
/// the flag never trades, which is the correct behaviour for a platform whose default posture is to do
/// nothing.
/// </para>
/// <para>
/// The loop itself is deliberately dull: it owns cadence, the operator-visible lease in
/// <see cref="BotRun"/>, per-tick timeouts, and the failure counters the risk engine reads back. It owns no
/// trading logic. Mutual exclusion between replicas is the executor's advisory lock, not this timer — two
/// schedulers may agree a bot is due, and only one will get the lock.
/// </para>
/// </remarks>
public sealed class BotSchedulerService(
    IServiceScopeFactory scopeFactory,
    IOptions<TradingOptions> options,
    ILogger<BotSchedulerService> logger) : BackgroundService
{
    private string LeaseOwner => options.Value.LeaseOwner is { Length: > 0 } owner ? owner : Environment.MachineName;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var settings = options.Value;

        if (!settings.SchedulerEnabled)
        {
            logger.LogInformation(
                "Bot scheduler is disabled (Trading:SchedulerEnabled = false). No bot will be evaluated.");
            return;
        }

        logger.LogInformation(
            "Bot scheduler started as lease owner {LeaseOwner}, polling every {PollSeconds}s, " +
            "at most {MaxBots} bots per cycle",
            LeaseOwner, settings.PollSeconds, settings.MaxBotsPerCycle);

        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(Math.Max(1, settings.PollSeconds)));

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await RunCycleAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                // A cycle that throws must not kill the loop; the next tick gets a clean attempt.
                logger.LogError(exception, "Bot scheduler cycle failed");
            }

            try
            {
                await timer.WaitForNextTickAsync(stoppingToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }

        logger.LogInformation("Bot scheduler stopped");
    }

    private async Task RunCycleAsync(CancellationToken stoppingToken)
    {
        var dueBots = await FindDueBotsAsync(stoppingToken);
        if (dueBots.Count == 0)
            return;

        logger.LogDebug("Bot scheduler found {Count} due bot(s)", dueBots.Count);

        // Sequential on purpose. Each tick talks to the engine and possibly a venue, and running them one
        // at a time keeps the load on both predictable and the logs readable. Bots are independent, so
        // parallelism buys latency the cadence does not need.
        foreach (var botId in dueBots)
        {
            if (stoppingToken.IsCancellationRequested)
                break;

            await RunOneBotAsync(botId, stoppingToken);
        }
    }

    private async Task<List<Guid>> FindDueBotsAsync(CancellationToken stoppingToken)
    {
        var settings = options.Value;
        var now = DateTime.UtcNow;

        using var scope = scopeFactory.CreateScope();
        var bots = scope.ServiceProvider.GetRequiredService<IRepo<TradingBot>>();

        // Only Active bots are candidates. Draft, Paused, Stopped and Faulted all mean "do not trade", and
        // a faulted bot in particular stays untouched until an operator has looked at why.
        return await bots.TableNoTracking
            .Where(b => b.Status == BotStatus.Active)
            .Where(b => b.LastTickAt == null
                        || b.LastTickAt.Value.AddSeconds(b.CadenceSeconds <= 0 ? 60 : b.CadenceSeconds) <= now)
            .OrderBy(b => b.LastTickAt ?? DateTime.MinValue)
            .Select(b => b.Id)
            .Take(Math.Max(1, settings.MaxBotsPerCycle))
            .ToListAsync(stoppingToken);
    }

    private async Task RunOneBotAsync(Guid botId, CancellationToken stoppingToken)
    {
        var settings = options.Value;

        // A tick that hangs — a wedged gRPC call, a venue that never answers — must not stall every other
        // bot behind it. The timeout abandons this tick only; the bot is picked up again next cycle.
        using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        timeoutSource.CancelAfter(TimeSpan.FromSeconds(Math.Max(5, settings.TickTimeoutSeconds)));
        var cancellationToken = timeoutSource.Token;

        using var scope = scopeFactory.CreateScope();
        var provider = scope.ServiceProvider;
        var runs = provider.GetRequiredService<IRepo<BotRun>>();

        BotRun? run = null;
        try
        {
            run = await LeaseRunAsync(provider, runs, botId, cancellationToken);
            if (run is null)
                return;

            var executor = provider.GetRequiredService<BotTickExecutor>();
            var outcome = await executor.ExecuteAsync(botId, cancellationToken);

            await RecordOutcomeAsync(runs, run, outcome, cancellationToken);

            if (outcome.Result is not (TickResult.Skipped or TickResult.AlreadyEvaluated))
            {
                logger.LogInformation(
                    "Bot {BotId} tick {Result}{Action} (correlation {CorrelationId}){Message}",
                    botId,
                    outcome.Result,
                    outcome.Action is null ? "" : $" [{outcome.Action}]",
                    outcome.CorrelationId,
                    outcome.Message is null ? "" : $": {outcome.Message}");
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException)
        {
            logger.LogWarning(
                "Bot {BotId} tick exceeded the {Timeout}s budget and was abandoned",
                botId, settings.TickTimeoutSeconds);
            await RecordFailureAsync(runs, run, "tick timed out");
        }
        catch (Exception exception)
        {
            logger.LogError(exception, "Bot {BotId} tick threw outside the executor", botId);
            await RecordFailureAsync(runs, run, exception.Message);
        }
    }

    /// <summary>
    /// Claims (or renews) the operator-visible lease for this bot, returning null when a live lease is held
    /// elsewhere.
    /// </summary>
    /// <remarks>
    /// This row is bookkeeping and a heartbeat, not the concurrency control — the executor's Postgres
    /// advisory lock is what actually prevents two workers from trading one bot. A lease whose heartbeat has
    /// gone stale is taken over, because the alternative is a bot that stops trading forever because the
    /// process that held its lease was killed.
    /// </remarks>
    private async Task<BotRun?> LeaseRunAsync(
        IServiceProvider provider,
        IRepo<BotRun> runs,
        Guid botId,
        CancellationToken cancellationToken)
    {
        var settings = options.Value;
        var now = DateTime.UtcNow;
        var owner = LeaseOwner;

        var existing = await runs.Table
            .Where(r => r.BotId == botId && r.EndedAt == null)
            .OrderByDescending(r => r.StartedAt)
            .FirstOrDefaultAsync(cancellationToken);

        if (existing is not null)
        {
            var staleAfter = now.AddSeconds(-Math.Max(30, settings.LeaseStaleSeconds));
            var isOurs = string.Equals(existing.LeaseOwner, owner, StringComparison.Ordinal);

            if (!isOurs && existing.LastHeartbeatAt > staleAfter)
                return null;

            if (!isOurs)
            {
                logger.LogWarning(
                    "Taking over the stale lease on bot {BotId} from {PreviousOwner} " +
                    "(last heartbeat {LastHeartbeat:O})",
                    botId, existing.LeaseOwner, existing.LastHeartbeatAt);
                existing.LeaseOwner = owner;
            }

            existing.LastHeartbeatAt = now;
            await runs.UpdateAsync(existing, saveNow: true, cancellationToken);
            return existing;
        }

        var bots = provider.GetRequiredService<IRepo<TradingBot>>();
        var mode = await bots.TableNoTracking
            .Where(b => b.Id == botId)
            .Select(b => (OperatingMode?)b.OperatingMode)
            .FirstOrDefaultAsync(cancellationToken);

        if (mode is null)
            return null;

        var run = new BotRun
        {
            BotId = botId,
            OperatingMode = mode.Value,
            LeaseOwner = owner,
            StartedAt = now,
            LastHeartbeatAt = now,
        };
        await runs.AddAsync(run, saveNow: true, cancellationToken);
        return run;
    }

    private static async Task RecordOutcomeAsync(
        IRepo<BotRun> runs,
        BotRun run,
        TickOutcome outcome,
        CancellationToken cancellationToken)
    {
        run.TickCount++;
        run.LastTickAt = DateTime.UtcNow;
        run.LastHeartbeatAt = run.LastTickAt.Value;

        if (outcome.RecordedDecision)
            run.DecisionCount++;

        if (outcome.PlacedOrder)
            run.OrderCount++;

        if (outcome.Result == TickResult.Faulted)
        {
            run.ErrorCount++;
            run.ConsecutiveFailureCount++;
            run.LastError = outcome.Message;
            run.LastErrorAt = run.LastTickAt;

            // A faulted bot is no longer Active, so this lease has nothing left to hold.
            run.EndedAt = run.LastTickAt;
        }
        else if (outcome.Result is TickResult.Hold or TickResult.Traded or TickResult.RiskDenied)
        {
            // The engine answered and the pipeline completed. A risk denial is a successful tick — the
            // platform asked and got a clear no — so it clears the failure streak rather than adding to it.
            run.ConsecutiveFailureCount = 0;
        }

        await runs.UpdateAsync(run, saveNow: true, cancellationToken);
    }

    private static async Task RecordFailureAsync(IRepo<BotRun> runs, BotRun? run, string message)
    {
        if (run is null)
            return;

        run.TickCount++;
        run.ErrorCount++;
        run.ConsecutiveFailureCount++;
        run.LastError = message;
        run.LastErrorAt = DateTime.UtcNow;
        run.LastHeartbeatAt = run.LastErrorAt.Value;

        // CancellationToken.None: the tick's own token may already be cancelled, and the failure it just
        // recorded is exactly the thing that must still reach the database.
        await runs.UpdateAsync(run, saveNow: true, CancellationToken.None);
    }
}
