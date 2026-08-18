namespace CryptoSignal.Infra.Tooling.Logging.Abstract;

public interface IOrderedSerilogConfig
{
    int Order { get; }
    bool IsEnabled { get; }
    string Name { get; }
}