namespace CryptoSignal.Api.Application.Trading.Instruments;

/// <summary>
/// Thrown when the trading grid for a symbol cannot be established.
/// </summary>
/// <remarks>
/// This is deliberately an exception and never a permissive default. Rules with a zero tick size, a zero
/// step size and no minimum notional describe a venue that accepts anything, which no venue does — an
/// order sized against those imaginary rules is rejected at the venue at best, and at worst is accepted
/// at a size nobody intended. The tick handler turns this into a bot fault.
/// </remarks>
public sealed class InstrumentRulesUnavailableException(string message, Exception? innerException = null)
    : Exception(message, innerException);
