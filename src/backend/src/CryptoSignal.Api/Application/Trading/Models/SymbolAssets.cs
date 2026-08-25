namespace CryptoSignal.Api.Application.Trading.Models;

/// <summary>
/// Splits a Binance-style concatenated symbol (<c>BTCUSDT</c>) into its base and quote assets.
/// </summary>
/// <remarks>
/// <para>
/// Only needed where no venue can be asked: <see cref="Domain.Enums.Trading.MarketVenue.Replay"/> has no
/// <c>exchangeInfo</c> endpoint. Every live venue reports <c>baseAsset</c> and <c>quoteAsset</c>
/// explicitly, and that report is always preferred over this guess.
/// </para>
/// <para>
/// The quote list is ordered longest-first so <c>USDC</c> is matched before <c>USDT</c> cannot shadow it,
/// and an unrecognised symbol throws. Defaulting the quote asset would misname the currency a balance
/// check reads and a fee is denominated in.
/// </para>
/// </remarks>
public static class SymbolAssets
{
    private static readonly string[] KnownQuotes =
        ["USDT", "USDC", "FDUSD", "TUSD", "BUSD", "TRY", "EUR", "BTC", "ETH", "BNB"];

    public static (string BaseAsset, string QuoteAsset) Split(string symbol)
    {
        if (string.IsNullOrWhiteSpace(symbol))
            throw new ArgumentException("A symbol is required.", nameof(symbol));

        var upper = symbol.Trim().ToUpperInvariant();

        foreach (var quote in KnownQuotes.OrderByDescending(q => q.Length))
        {
            if (upper.Length > quote.Length && upper.EndsWith(quote, StringComparison.Ordinal))
                return (upper[..^quote.Length], quote);
        }

        throw new ArgumentException(
            $"'{symbol}' does not end in a quote asset this platform recognises " +
            $"({string.Join(", ", KnownQuotes)}). Ask the venue for the split instead of guessing it.",
            nameof(symbol));
    }
}
