using Microsoft.Extensions.Logging;

namespace CryptoSignal.Infra.Tooling.Logging.Adapters;

public class LoggerAdapter<T>(ILogger<T> logger) : ILoggerAdapter<T>
{
    public void Info(string message, params object[] args) => logger.LogInformation(message, args);
    public void Warning(string message, params object[] args) => logger.LogWarning(message, args);
    public void Error(Exception ex, string message, params object[] args) => logger.LogError(ex, message, args);
    public void Debug(string message, params object[] args) => logger.LogDebug(message, args);
    public IDisposable BeginScope<TState>(TState state) where TState : notnull
        => logger.BeginScope(state);
}