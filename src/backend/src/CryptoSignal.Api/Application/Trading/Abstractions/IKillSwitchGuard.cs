using CryptoSignal.Api.Domain.Models.Trading;

namespace CryptoSignal.Api.Application.Trading.Abstractions;

/// <summary>
/// Answers whether any engaged kill switch covers a bot, before a tick does any work.
/// </summary>
/// <remarks>
/// This duplicates the risk engine's check 14 on purpose, at a different point. The engine's check is the
/// <b>authoritative gate</b> — nothing reaches a broker without it. This guard is the <b>early exit</b>:
/// it runs before the candle fetch and the engine round trip, so engaging a switch stops the work as well
/// as the order. Removing either would be a mistake: without the guard a halted platform still hammers
/// the exchange and the ML engine; without the check a code path that forgot the guard could still trade.
/// </remarks>
public interface IKillSwitchGuard
{
    /// <summary>Every engaged switch whose scope covers the bot. Empty is the only clear state.</summary>
    Task<IReadOnlyList<KillSwitch>> GetBlockingAsync(TradingBot bot, CancellationToken cancellationToken);
}
