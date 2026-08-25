using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Api.Application.Trading.Risk;

/// <summary>Reads the engaged switches covering one bot.</summary>
/// <remarks>
/// The scopes are ORed, never ranked: a bot-scoped switch cannot unblock what a global switch stopped,
/// and a narrow switch is not an exemption from a wider one. Written as a single predicate so there is no
/// ordering to get wrong.
/// </remarks>
public sealed class KillSwitchGuard(IRepo<KillSwitch> killSwitches)
    : IKillSwitchGuard, IScopedSvcMarker
{
    public async Task<IReadOnlyList<KillSwitch>> GetBlockingAsync(
        TradingBot bot,
        CancellationToken cancellationToken) =>
        await killSwitches.TableNoTracking
            .Where(k => k.IsEngaged
                        && (k.Scope == KillSwitchScope.Global
                            || (k.Scope == KillSwitchScope.OperatingMode &&
                                k.ScopeOperatingMode == bot.OperatingMode)
                            || (k.Scope == KillSwitchScope.Exchange && k.ScopeVenue == bot.Venue)
                            || (k.Scope == KillSwitchScope.Bot && k.ScopeBotId == bot.Id)
                            || (k.Scope == KillSwitchScope.Symbol && k.ScopeSymbol == bot.Symbol)))
            .OrderBy(k => k.Scope)
            .ToListAsync(cancellationToken);
}
