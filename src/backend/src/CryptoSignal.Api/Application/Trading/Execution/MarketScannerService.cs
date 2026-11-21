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

        // Scoped services (repos, ticker source, engine client) resolve per pass inside one scope.
        using var scope = scopeFactory.CreateScope();
        var tickerSource = scope.ServiceProvider.GetRequiredService<IBinanceFuturesTickerSource>();
        var engine = scope.ServiceProvider.GetRequiredService<IMlServiceClient>();
        var marketData = scope.ServiceProvider.GetRequiredService<IMarketDataSourceResolver>();
        var signalsRepo = scope.ServiceProvider.GetRequiredService<IRepo<ScannerSignal>>();

        var tickers = await tickerSource.GetTickersAsync(cancellationToken);
        if (tickers.Count == 0)
        {
            logger.LogWarning("Scanner found no tickers — skipping cycle.");
            return;
        }

        // Binance lists a handful of symbols with non-ASCII names (e.g. a Chinese-titled token). The
        // engine's ticker contract is uppercase alphanumerics, and a whole scan must not die on one
        // untradeable name — so they are filtered before ranking rather than skipped mid-pass.
        var topSymbols = tickers
            .Where(t => System.Text.RegularExpressions.Regex.IsMatch(t.Symbol, "^[A-Z0-9]{2,}$"))
            .Take(settings.MaxSymbolsPerPass)
            .ToList();
        logger.LogInformation(
            "Scanner pass {ScanId}: top symbols {Symbols}",
            scanId, string.Join(",", topSymbols.Select(t => t.Symbol)));

        var source = marketData.Resolve(settings.Venue);
        var windows = new List<(ScannerTicker Ticker, IReadOnlyList<MarketCandleData> Candles)>();
        // Bounded fan-out. A pass over a few hundred symbols is dominated by the venue round trip, and
        // the weight budget (not the CPU) is what bounds concurrency — eight in flight is well inside
        // Binance's 2,400/min for a 5-minute cadence.
        var gate = new SemaphoreSlim(Math.Max(1, settings.MaxConcurrency));
        var fetched = new System.Collections.Concurrent.ConcurrentBag<(ScannerTicker, IReadOnlyList<MarketCandleData>)>();
        await Task.WhenAll(topSymbols.Select(async ticker =>
        {
            await gate.WaitAsync(cancellationToken);
            try
            {
                var candles = await source.GetClosedCandlesAsync(
                    ticker.Symbol, settings.Interval, settings.CandleCount, cancellationToken);
                fetched.Add((ticker, candles));
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                // One symbol's feed failing must not mute the rest of the universe.
                logger.LogWarning(
                    "Scanner skipping {Symbol}: candle window unavailable: {Message}",
                    ticker.Symbol, exception.Message);
            }
            finally
            {
                gate.Release();
            }
        }));
        windows.AddRange(fetched);

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

        var modelSpec = settings.ModelEnabled
            ? new MlScanModelSpec(
                settings.ModelTakeProfitAtr,
                settings.ModelStopLossAtr,
                settings.ModelMinimumConfidence,
                settings.ModelMinimumExpectedPoints,
                settings.ModelMaxHoldingPeriods)
            : null;

        var results = await engine.ScanSymbolsAsync(
            scanSymbols,
            strategySpecs,
            settings.Interval,
            modelSpec,
            cancellationToken,
            settings.ScanDeadlineSeconds);

        // A symbol with a model verdict is not also recorded from the zoo: the model prices the same
        // bet in R, and two rows for one symbol would make a ScannerBot claim whichever landed first.
        var modelBySymbol = results
            .Where(r => r.ModelPriced)
            .GroupBy(r => r.Symbol)
            .ToDictionary(
                g => g.Key,
                g => g.OrderByDescending(r => r.ExpectedPoints).First());

        var tickerBySymbol = topSymbols.ToDictionary(t => t.Symbol, t => t);
        var atrBySymbol = windows.ToDictionary(
            w => w.Ticker.Symbol, w => AverageTrueRange(w.Candles, 14));

        var recorded = 0;
        var priced = 0;
        var withPoints = 0;
        foreach (var result in results)
        {
            if (string.IsNullOrEmpty(result.Direction))
                continue;

            var isLong = result.Direction == "LONG";
            if (!isLong && result.Direction != "SHORT")
                continue;

            // A model row is authoritative for its symbol: skip the zoo's duplicate. When the model pass
            // is enabled the zoo rows are dropped entirely — otherwise Score would compare expected R
            // against the liquidity×move heuristic in one column, and the bot would claim whichever
            // number happened to be bigger.
            if (modelSpec is not null && !result.ModelPriced)
                continue;
            if (!result.ModelPriced
                && modelBySymbol.TryGetValue(result.Symbol, out var modelRow)
                && modelRow.Direction == result.Direction)
            {
                continue;
            }

            tickerBySymbol.TryGetValue(result.Symbol, out var ticker);
            atrBySymbol.TryGetValue(result.Symbol, out var atr);

            await signalsRepo.AddAsync(new ScannerSignal
            {
                ScanId = scanId,
                Symbol = result.Symbol,
                Interval = settings.Interval,
                StrategyKey = result.ModelPriced ? "model" : result.Strategy,
                Direction = isLong ? SignalDirection.Long : SignalDirection.Short,
                Confidence = result.ModelPriced ? result.ModelConfidence : result.Confidence,
                // The ranking statistic is expected R when the model priced the symbol, and the
                // ticker's liquidity×move score for zoo-only rows. One number, two honest meanings,
                // both documented on the column's consumer (ScannerController ordering).
                Score = result.ModelPriced
                    ? (result.PointsAvailable
                        ? (decimal)result.ExpectedPoints
                        // No points head on this bundle yet: rank by the calibrated confidence the model
                        // did produce, rather than writing a column of zeros that makes every signal
                        // indistinguishable to the claimer.
                        : (decimal)result.ModelConfidence)
                    : ticker is null ? 0m : ScanScore(ticker),
                AtrAtSignal = atr,
                Reason = result.ModelPriced
                    ? $"{result.Reason} | points={result.ExpectedPoints:+0.000;-0.000}R"
                    : result.Reason,
            }, saveNow: true, cancellationToken);
            recorded++;
            if (result.ModelPriced)
            {
                priced++;
                if (result.PointsAvailable)
                    withPoints++;
            }
        }

        logger.LogInformation(
            "Scanner pass {ScanId} complete: {Recorded} signals from {Symbols} symbols " +
            "({Priced} model-priced, {WithPoints} with a points head), {Strategies} strategies each",
            scanId, recorded, windows.Count, priced, withPoints, strategySpecs.Length);
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

    /// <summary>
    /// Candle fetches in flight per pass. The venue's request-weight allowance, not the CPU, is the
    /// real ceiling: 300-candle klines are weight 2 each, so eight concurrent is ~16 weight against a
    /// 2,400/min budget even when a pass over hundreds of symbols takes tens of seconds.
    /// </summary>
    public int MaxConcurrency { get; set; } = 8;

    /// <summary>
    /// Ask the engine to price every scanned symbol with the ML model in the same scan call. When a
    /// symbol is priced, its model row is the one recorded — the zoo's duplicate is skipped.
    /// </summary>
    public bool ModelEnabled { get; set; } = true;

    /// <summary>ATR bracket the model prices each scanned symbol at.</summary>
    public double ModelTakeProfitAtr { get; set; } = 1.5;
    public double ModelStopLossAtr { get; set; } = 1.0;

    /// <summary>Floors the model row must clear to be recorded. 0 = any positive expectancy.</summary>
    public double ModelMinimumConfidence { get; set; } = 0.0;
    public double ModelMinimumExpectedPoints { get; set; } = 0.0;

    /// <summary>
    /// Budget for one market-wide scan RPC. Scaling with the listing is the point: a pass prices every
    /// candidate symbol, so the interactive deadline (seconds) fails as soon as the exchange lists more
    /// pairs than the box can score in ten seconds — which is every pass once training shares the CPU.
    /// </summary>
    public int ScanDeadlineSeconds { get; set; } = 180;

    /// <summary>Holding horizon handed to the engine; 0 defers to the bundle's own label horizon.</summary>
    public int ModelMaxHoldingPeriods { get; set; } = 0;

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
