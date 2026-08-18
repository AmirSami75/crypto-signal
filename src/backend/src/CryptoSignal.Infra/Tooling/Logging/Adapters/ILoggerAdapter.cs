namespace CryptoSignal.Infra.Tooling.Logging.Adapters;

public interface ILoggerAdapter<T>
{

    void Info(string message, params object[] args );
    void Warning(string message, params object[] args);
    void Error(Exception ex, string message, params object[] args);
    void Debug(string message, params object[] args);
    IDisposable BeginScope<TState>(TState state);

}
