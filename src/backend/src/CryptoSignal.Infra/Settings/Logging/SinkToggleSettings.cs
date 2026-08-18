namespace CryptoSignal.Infra.Settings.Logging;

public sealed class SinkToggleSettings
{
    public bool Console { get; set; } = true;
    public bool File { get; set; } = true;
    public bool Elastic { get; set; } = true;
}