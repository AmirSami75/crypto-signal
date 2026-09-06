using CryptoSignal.Api.Application.Trading.Abstractions;
using CryptoSignal.Api.Application.Trading.MarketData;
using CryptoSignal.Api.Application.Trading.Models;
using CryptoSignal.Api.Clients;
using CryptoSignal.Api.Contracts;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace CryptoSignal.Api.Application.Trading.Execution;

/// <summary>
/// Periodically scans the market for strategy-zoo signals and records them as proposals.
/// Scanner-mode bots claim these proposals in <see cref="BotTickExecutor"/>.
/// </summary>
/// <remarks>
/// <para>
/// Each cycle: fetch the venue's 24h tickers, rank symbols by
/// <c>|change%| × log10(quoteVolume)</c>, take the top N, fetch recent candles per symbol,
/// and ask the engine's <c>ScanSymbols</c> RPC to run the configured zoo strategies.
/// Hits are persisted as <see cref="ScannerSignal"/> rows — proposals, never orders.
/// </para>
/// <para>
/// Disabled by default (<see cref="ScannerOptions.Enabled"/>). Weight budget: the tickers call is
/// one request; candles are N requests of weight 2 each, so N is capped at 20 by default config —
/// far under the venue's per-minute allowance.
/// </para>
/// </remarks>
public sealed class MarketScannerService(
    IServiceScopeFactory scopeFactory,
    IBinanceFuturesTickerSource tickerSource,
    IMlServiceClient engine,
    IMarketDataSourceResolver marketData,
    IOptions<ScannerOptions> options,
    ILogger<MarketScannerService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var settings = options.Value;
        if (!settings.Enabled)
        {
            logger.LogInformation(
                "Market scanner is disabled (Scanner:Enabled = false). No signals will be proposed.");
            return;
        }

        logger.LogInformation(
            "Market scanner started: every {Interval}min, top {Max} {Interval0} symbols, strategies={Strategies}",
            settings.ScanIntervalMinutes, settings.MaxSymbolsPerPass, settings.Interval,
            string.Join(",", settings.StrategyKeys));

        // One cycle immediately, then on the timer. The timer path catches everything so one bad
        // cycle never kills the loop; the immediate call lets a misconfigured scanner fail loudly
        // in the first minute rather than after the first interval.
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await RunScanAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Market scanner cycle failed — retrying next interval.");
            }

            try
            {
                await Task.Delay(TimeSpan.FromMinutes(settings.ScanIntervalMinutes), stoppingToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }
    }

    private async Task RunScanAsync(CancellationToken cancellationToken)
    {
        var settings = options.Value;
        var scanId = Guid.CreateVersion7();

        var tickers = await tickerSource.GetTickersAsync(cancellationToken);
        if (tickers.Count == 0)
        {
            logger.LogWarning("Scanner found no tickers — skipping cycle.");
            return;
        }

        var topSymbols = tickers.Take(settings.MaxSymbolsPerPass).ToList();
        logger.LogInformation(
            "Scanner pass {ScanId}: top symbols {Symbols}",
            scanId, string.Join(",", topSymbols.Select(t => t.Symbol)));

        var source = marketData.Resolve(settings.Venue);
        var windows = new List<(ScannerTicker Ticker, IReadOnlyList<MarketCandleData> Candles)>();
        foreach (var ticker in topSymbols)
        {
            try
            {
                var candles = await source.GetClosedCandlesAsync(
                    ticker.Symbol, settings.Interval, settings.CandleCount, cancellationToken);
                windows.Add((ticker, candles));
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                // One symbol's feed failing must not mute the other nineteen.
                logger.LogWarning(
                    "Scanner skipping {Symbol}: candle window unavailable: {Message}",
                    ticker.Symbol, exception.Message);
            }
        }

        if (windows.Count == 0)
        {
            logger.LogWarning("Scanner fetched no candle windows — skipping cycle.");
            return;
        }

        var strategySpecs = settings.StrategyKeys
            .Select(key => new MlScanStrategy(
                key, settings.DefaultTakeProfitAtr, settings.DefaultStopLossAtr))
            .ToArray();
        var scanSymbols = windows
            .Select(w => new MlScanSymbol(
                w.Ticker.Symbol,
                w.Candles.Select(c => new MlCandle(
                    c.OpenTime, c.Open, c.High, c.Low, c.Close, c.Volume)).ToList()))
            .ToList();

        var results = await engine.ScanSymbolsAsync(
            scanSymbols, strategySpecs, settings.Interval, cancellationToken);

        var tickerBySymbol = topSymbols.ToDictionary(t => t.Symbol, t => t);
        var atrBySymbol = windows.ToDictionary(
            w => w.Ticker.Symbol, w => AverageTrueRange(w.Candles, 14));

        using var scope = scopeFactory.CreateScope();
        var signalsRepo = scope.ServiceProvider.GetRequiredService<IRepo<ScannerSignal>>();

        var recorded = 0;
        foreach (var result in results)
        {
            if (string.IsNullOrEmpty(result.Direction))
                continue;

            var isLong = result.Direction == "LONG";
            if (!isLong && result.Direction != "SHORT")
                continue;

            tickerBySymbol.TryGetValue(result.Symbol, out var ticker);
            atrBySymbol.TryGetValue(result.Symbol, out var atr);

            await signalsRepo.AddAsync(new ScannerSignal
            {
                ScanId = scanId,
                Symbol = result.Symbol,
                Interval = settings.Interval,
                StrategyKey = result.Strategy,
                Direction = isLong ? SignalDirection.Long : SignalDirection.Short,
                Confidence = result.Confidence,
                Score = ticker is null ? 0m : ScanScore(ticker),
                AtrAtSignal = atr,
                Reason = result.Reason,
            }, saveNow: true, cancellationToken);
            recorded++;
        }

        logger.LogInformation(
            "Scanner pass {ScanId} complete: {Recorded} signals from {Symbols} symbols, " +
            "{Strategies} strategies each",
            scanId, recorded, windows.Count, strategySpecs.Length);
    }

    /// <summary>The scanner's ranking score: |24h change %| × log10(quote volume).</summary>
    private static decimal ScanScore(ScannerTicker ticker) =>
        (decimal)(
            Math.Abs((double)ticker.PriceChangePercent) *
            Math.Log10(Math.Max(1.0, (double)ticker.QuoteVolume)));

    /// <summary>
    /// Mean true range over the last <paramref name="window"/> candles, in price units.
    /// The same quantity the engine's ATR columns are built from, so the bracket a scanner
    /// bot prices from <see cref="ScannerSignal.AtrAtSignal"/> matches its features.
    /// </summary>
    private static decimal AverageTrueRange(IReadOnlyList<MarketCandleData> candles, int window)
    {
        if (candles.Count < 2)
            return 0m;

        var start = Math.Max(1, candles.Count - window);
        decimal sum = 0m;
        var count = 0;
        for (var i = start; i < candles.Count; i++)
        {
            var previousClose = candles[i - 1].Close;
            var trueRange = Math.Max(
                candles[i].High - candles[i].Low,
                Math.Max(
                    Math.Abs(candles[i].High - previousClose),
                    Math.Abs(candles[i].Low - previousClose)));
            sum += trueRange;
            count++;
        }

        return count == 0 ? 0m : sum / count;
    }
}

/// <summary>Options for the market scanner (binds <c>Scanner</c> in appsettings).</summary>
public sealed class ScannerOptions
{
    public const string SectionName = "Scanner";

    /// <summary>Whether the scanner background service runs. Off by default.</summary>
    public bool Enabled { get; set; }

    /// <summary>Minutes between scan passes.</summary>
    public int ScanIntervalMinutes { get; set; } = 5;

    /// <summary>Symbols evaluated per pass, ranked by 24h change × volume.</summary>
    public int MaxSymbolsPerPass { get; set; } = 20;

    /// <summary>Closed candles fetched per symbol per pass.</summary>
    public int CandleCount { get; set; } = 300;

    /// <summary>Candle interval the zoo strategies are evaluated on.</summary>
    public string Interval { get; set; } = "5m";

    /// <summary>Venue supplying tickers and candles.</summary>
    public Domain.Enums.Trading.MarketVenue Venue { get; set; } =
        Domain.Enums.Trading.MarketVenue.BinanceFuturesTestnet;

    /// <summary>Strategy-zoo keys to evaluate every pass.</summary>
    public string[] StrategyKeys { get; set; } = [];

    /// <summary>Bracket distances (ATR multiples) recorded with each signal.</summary>
    public double DefaultTakeProfitAtr { get; set; } = 1.5;
    public double DefaultStopLossAtr { get; set; } = 1.0;
}
