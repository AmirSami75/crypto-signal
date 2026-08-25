using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.DTOs.Trading;

/// <summary>
/// A request to engage a kill switch.
/// </summary>
/// <remarks>
/// <para>
/// Engaging blocks <b>new</b> intents and submissions within the scope. It does not cancel the orders
/// already working at the venue, and it does not close open positions: mass cancellation can itself fail
/// or increase risk, and conflating the two would make the emergency stop the riskiest button on the
/// platform. Cancelling is a separate, explicit action.
/// </para>
/// <para>
/// Exactly one scope field is meaningful, selected by <see cref="Scope"/>. A <c>Global</c> switch needs
/// none of them.
/// </para>
/// </remarks>
public sealed record KillSwitchInputDto
{
    public KillSwitchScope Scope { get; init; } = KillSwitchScope.Global;

    /// <summary>Required when <see cref="Scope"/> is <c>OperatingMode</c>.</summary>
    public OperatingMode? ScopeOperatingMode { get; init; }

    /// <summary>Required when <see cref="Scope"/> is <c>Exchange</c>.</summary>
    public MarketVenue? ScopeVenue { get; init; }

    /// <summary>Required when <see cref="Scope"/> is <c>Bot</c>.</summary>
    public Guid? ScopeBotId { get; init; }

    /// <summary>Required when <see cref="Scope"/> is <c>Symbol</c>.</summary>
    public string? ScopeSymbol { get; init; }

    /// <summary>Why. Required — an unexplained halt is not auditable.</summary>
    public string Reason { get; init; } = string.Empty;
}

/// <summary>A kill switch and its engagement history.</summary>
public sealed record KillSwitchDto(
    Guid Id,
    KillSwitchScope Scope,
    OperatingMode? ScopeOperatingMode,
    MarketVenue? ScopeVenue,
    Guid? ScopeBotId,
    string? ScopeSymbol,
    bool IsEngaged,
    string Reason,
    bool IsAutomatic,
    string? TriggerDetail,
    DateTime? EngagedAt,
    string? EngagedByUserName,
    DateTime? DisengagedAt,
    string? DisengagedByUserName,
    DateTime CreatedAt);
