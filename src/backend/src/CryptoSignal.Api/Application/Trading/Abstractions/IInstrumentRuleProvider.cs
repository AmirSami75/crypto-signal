using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Domain.Enums.Trading;

namespace CryptoSignal.Api.Application.Trading.Abstractions;

/// <summary>Supplies a venue's trading filters for one symbol.</summary>
/// <remarks>
/// A provider that cannot answer must throw rather than return a permissive default. Fabricating
/// "tick size 0, no minimum" would let an order through every parameter check by describing a venue
/// that does not exist — the failure mode the safety policy calls treating missing data as permission
/// to trade.
/// </remarks>
public interface IInstrumentRuleProvider
{
    Task<InstrumentRules> GetRulesAsync(
        MarketVenue venue,
        string symbol,
        CancellationToken cancellationToken);
}
