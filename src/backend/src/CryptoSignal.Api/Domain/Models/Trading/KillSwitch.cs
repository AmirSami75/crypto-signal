using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Api.Domain.Models.Trading;

/// <summary>
/// A switch that blocks new intents and submissions within its scope. Scopes are independent and are
/// checked together, so a bot is blocked if <i>any</i> engaged switch covers it.
/// </summary>
/// <remarks>
/// <para>
/// Engaging a switch blocks new orders and nothing else. Cancelling the orders already working at the
/// venue is a separate, explicit action, because mass cancellation can itself fail or increase risk —
/// conflating the two would make the emergency stop the riskiest button on the platform.
/// </para>
/// <para>
/// The scope columns are mutually exclusive by convention rather than by constraint: exactly one is
/// populated, chosen by <see cref="Scope"/>. <see cref="Scope"/> is the discriminator, and a reader
/// that switches on it never has to guess which column is meaningful.
/// </para>
/// </remarks>
public class KillSwitch : BaseEntity
{
    /// <summary>How wide the switch reaches. Selects which scope column below is populated.</summary>
    public KillSwitchScope Scope { get; set; }

    /// <summary>The mode blocked, when <see cref="Scope"/> is <c>OperatingMode</c>.</summary>
    public OperatingMode? ScopeOperatingMode { get; set; }

    /// <summary>The venue blocked, when <see cref="Scope"/> is <c>Exchange</c>.</summary>
    public MarketVenue? ScopeVenue { get; set; }

    /// <summary>The bot blocked, when <see cref="Scope"/> is <c>Bot</c>.</summary>
    public Guid? ScopeBotId { get; set; }

    /// <summary>The symbol blocked, when <see cref="Scope"/> is <c>Symbol</c>.</summary>
    public string? ScopeSymbol { get; set; }

    /// <summary>Whether the switch is currently blocking.</summary>
    public bool IsEngaged { get; set; }

    /// <summary>Why it was engaged. Required — an unexplained halt is not auditable.</summary>
    public string Reason { get; set; } = string.Empty;

    /// <summary>True when a platform trigger engaged it rather than a person.</summary>
    public bool IsAutomatic { get; set; }

    /// <summary>Which trigger fired, for an automatic engagement.</summary>
    public string? TriggerDetail { get; set; }

    public DateTime? EngagedAt { get; set; }

    public Guid? EngagedByUserId { get; set; }

    public string? EngagedByUserName { get; set; }

    public DateTime? DisengagedAt { get; set; }

    public Guid? DisengagedByUserId { get; set; }

    public string? DisengagedByUserName { get; set; }
}
