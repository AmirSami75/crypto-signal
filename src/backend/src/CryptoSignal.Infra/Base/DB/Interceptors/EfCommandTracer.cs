using System;
using System.Collections.Concurrent;
using System.Data.Common;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore.Diagnostics;
using CryptoSignal.Infra.Base.Markers;
using CryptoSignal.Infra.Settings.Logging;
using CryptoSignal.Infra.Tooling.Logging.Adapters;

namespace CryptoSignal.Infra.Base.DB.Interceptors;

/// <summary>
/// Traces EF Core SQL commands with elapsed time and (optionally) parameters.
/// Configurable via API_Settings:Logging:EfCommandTracer (no IOptionsMonitor).
/// Logs success, failure, and cancellation for sync/async.
/// </summary>
public sealed class EfCommandTracer : DbCommandInterceptor, ISingletonInfraMarker
{
    private readonly ILoggerAdapter<EfCommandTracer> _log;
    private readonly EfCommandTracerSettings _opt;

    // One stopwatch per EF command execution
    private readonly ConcurrentDictionary<Guid, Stopwatch> _timers = new();

    public EfCommandTracer(ILoggerAdapter<EfCommandTracer> log, LoggingSettings settings)
    {
        _log = log ?? throw new ArgumentNullException(nameof(log));
        _opt = settings?.EfCommandTracer ?? new EfCommandTracerSettings();
    }

    private bool Enabled => _opt.Enabled;

    // -------------------- EXECUTING (start timing) --------------------
    public override InterceptionResult<DbDataReader> ReaderExecuting(
        DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result)
    {
        Start(eventData);
        return result;
    }

    public override InterceptionResult<object> ScalarExecuting(
        DbCommand command, CommandEventData eventData, InterceptionResult<object> result)
    {
        Start(eventData);
        return result;
    }

    public override InterceptionResult<int> NonQueryExecuting(
        DbCommand command, CommandEventData eventData, InterceptionResult<int> result)
    {
        Start(eventData);
        return result;
    }

    public override ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result,
        CancellationToken cancellationToken = default)
    {
        Start(eventData);
        return ValueTask.FromResult(result);
    }

    public override ValueTask<InterceptionResult<object>> ScalarExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<object> result,
        CancellationToken cancellationToken = default)
    {
        Start(eventData);
        return ValueTask.FromResult(result);
    }

    public override ValueTask<InterceptionResult<int>> NonQueryExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<int> result,
        CancellationToken cancellationToken = default)
    {
        Start(eventData);
        return ValueTask.FromResult(result);
    }

    // -------------------- EXECUTED (stop timing + log) --------------------
    public override DbDataReader ReaderExecuted(
        DbCommand command, CommandExecutedEventData eventData, DbDataReader result)
    {
        StopAndLog(command, eventData, outcome: "OK", rows: null);
        return result;
    }

    public override object? ScalarExecuted(
        DbCommand command, CommandExecutedEventData eventData, object? result)
    {
        StopAndLog(command, eventData, outcome: "OK", rows: 1);
        return result;
    }

    public override int NonQueryExecuted(
        DbCommand command, CommandExecutedEventData eventData, int result)
    {
        StopAndLog(command, eventData, outcome: "OK", rows: result);
        return result;
    }

    public override ValueTask<DbDataReader> ReaderExecutedAsync(
        DbCommand command, CommandExecutedEventData eventData, DbDataReader result,
        CancellationToken cancellationToken = default)
    {
        StopAndLog(command, eventData, outcome: "OK", rows: null);
        return ValueTask.FromResult(result);
    }

    public override ValueTask<object?> ScalarExecutedAsync(
        DbCommand command, CommandExecutedEventData eventData, object? result,
        CancellationToken cancellationToken = default)
    {
        StopAndLog(command, eventData, outcome: "OK", rows: 1);
        return ValueTask.FromResult(result);
    }

    public override ValueTask<int> NonQueryExecutedAsync(
        DbCommand command, CommandExecutedEventData eventData, int result,
        CancellationToken cancellationToken = default)
    {
        StopAndLog(command, eventData, outcome: "OK", rows: result);
        return ValueTask.FromResult(result);
    }

    // -------------------- FAILED / CANCELED --------------------
    public override void CommandFailed(DbCommand command, CommandErrorEventData eventData)
    {
        StopAndLog(command, eventData, outcome: "FAIL", rows: null, exception: eventData.Exception);
    }

    public override Task CommandFailedAsync(
        DbCommand command, CommandErrorEventData eventData, CancellationToken cancellationToken = default)
    {
        StopAndLog(command, eventData, outcome: "FAIL", rows: null, exception: eventData.Exception);
        return Task.CompletedTask;
    }

    public override void CommandCanceled(DbCommand command, CommandEndEventData eventData)
    {
        StopAndLog(command, eventData, outcome: "CANCEL", rows: null);
    }

    public override Task CommandCanceledAsync(
        DbCommand command, CommandEndEventData eventData, CancellationToken cancellationToken = default)
    {
        StopAndLog(command, eventData, outcome: "CANCEL", rows: null);
        return Task.CompletedTask;
    }

    // -------------------- INTERNALS --------------------
    private void Start(CommandEventData e)
    {
        if (!Enabled) return;
        _timers[e.CommandId] = Stopwatch.StartNew();
    }

    private void StopAndLog(
        DbCommand cmd,
        CommandEndEventData e,
        string outcome,
        int? rows,
        Exception? exception = null)
    {
        // Always remove timer if present (prevents leaks even if logging is disabled later)
        long elapsedMs;
        if (_timers.TryRemove(e.CommandId, out var sw))
        {
            sw.Stop();
            elapsedMs = sw.ElapsedMilliseconds;
        }
        else
        {
            // If Start never ran, EF provides duration in end event
            elapsedMs = (long)e.Duration.TotalMilliseconds;
        }

        // hard disable (no overhead beyond timer cleanup above)
        if (!Enabled) return;

        if (_opt.MinDurationMs > 0 && elapsedMs < _opt.MinDurationMs)
            return;

        var commandText = _opt.LogCommandText ? cmd.CommandText : "-";
        var parms = BuildParams(cmd);

        if (exception is null)
        {
            _log.Info("EFSQL {Outcome} ({Elapsed} ms) rows={Rows} | {CommandText} | params: {Params}",
                outcome, elapsedMs, rows, commandText, parms);
        }
        else
        {
            _log.Error(exception, "EFSQL {Outcome} ({Elapsed} ms) rows={Rows} | {CommandText} | params: {Params}",
                outcome, elapsedMs, rows, commandText, parms);
        }
    }

    private string BuildParams(DbCommand cmd)
    {
        if (!_opt.LogParameters) return "-";
        if (cmd.Parameters.Count == 0) return "-";

        return string.Join(", ",
            cmd.Parameters.Cast<DbParameter>()
                .Select(p => $"{p.ParameterName}={Printable(p.Value, _opt.MaxValueLength)}"));
    }

    private static object Printable(object? value, int maxLen) =>
        value is null or DBNull ? "NULL"
        : value is string s && s.Length > maxLen ? s[..maxLen] + "…"
        : value!;
}