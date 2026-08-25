using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>
/// Which venue a bot's orders actually reach. Stamped on every trading record and filtered on every
/// read, so paper and sandbox never share a portfolio, an order chain, or a performance series.
/// </summary>
/// <remarks>
/// <see cref="Paper"/> is the platform default and the safety invariant — see
/// <c>docs/LIVE_TRADING_SAFETY.md</c>. <see cref="Live"/> exists here only so the mode column can
/// express it; live execution is gated behind promotion gates this codebase does not implement, and
/// the fail-closed defaults deny it.
/// </remarks>
public enum OperatingMode
{
    /// <summary>Simulated fills against recorded candles. No credentials, no venue.</summary>
    [Display(Name = "Paper")] Paper = 1,

    /// <summary>Real orders against the exchange testnet. Worthless funds, real order lifecycle.</summary>
    [Display(Name = "Sandbox")] Sandbox = 2,

    /// <summary>Real orders against the production exchange. Not enabled.</summary>
    [Display(Name = "Live")] Live = 3,
}
