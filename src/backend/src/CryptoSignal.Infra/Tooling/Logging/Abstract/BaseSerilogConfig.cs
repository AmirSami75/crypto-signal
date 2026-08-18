using Microsoft.Extensions.Configuration;
using Serilog;

namespace CryptoSignal.Infra.Tooling.Logging.Abstract;

public abstract class BaseSerilogConfig(IConfiguration configuration) : IOrderedSerilogConfig
{
    protected IConfiguration Configuration { get; } = configuration;

    public virtual int Order => 0;
    public virtual string Name => GetType().Name;

    public virtual bool IsEnabled =>
        Configuration.GetValue<bool>($"API_Settings:Logging:Sinks:{Name}:Enabled", true);


    public abstract LoggerConfiguration Configure(LoggerConfiguration loggerConfig);
}