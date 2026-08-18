namespace CryptoSignal.Infra.Settings.Logging;

public class EfCommandTracerSettings
{
    public bool Enabled { get; init; } = true;
    public bool LogCommandText { get; init; } = true;
    public bool LogParameters { get; init; } = true;
    public int MaxValueLength { get; init; } = 120;
    public int MinDurationMs { get; set; } = 0;
}