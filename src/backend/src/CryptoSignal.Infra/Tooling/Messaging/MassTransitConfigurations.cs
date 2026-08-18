using MassTransit;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using CryptoSignal.Infra.Settings;

namespace CryptoSignal.Infra.Tooling.Messaging;

public static class MassTransitConfiguration
{
    public static void AddMassTransitWithRabbitMq(
        this IServiceCollection services,
        Action<IBusRegistrationConfigurator> configureBus = null,
        Action<IRabbitMqBusFactoryConfigurator, IBusRegistrationContext> configureRabbitMq = null)
    {
        var env = Environment.GetEnvironmentVariable("ASPNETCORE_ENVIRONMENT")?.ToLower();
        services.AddMassTransit(x =>
        {
            configureBus?.Invoke(x);

            x.SetEndpointNameFormatter(env switch
            {
                "development" => new KebabCaseEndpointNameFormatter("dev", false),
                "sandbox" => new KebabCaseEndpointNameFormatter("sand", false),
                "production" => new KebabCaseEndpointNameFormatter("prod", false),
                _ => new KebabCaseEndpointNameFormatter("local", false)
            });

            x.UsingRabbitMq((context, cfg) =>
            {
                var rabbitOpts = context.GetRequiredService<IOptions<RabbitMQSettings>>().Value;

                cfg.Host(
                    rabbitOpts.Host,
                    (ushort)rabbitOpts.Port,
                    rabbitOpts.Vhosts,
                    h =>
                    {
                        if (!string.IsNullOrWhiteSpace(rabbitOpts.UserName))
                            h.Username(rabbitOpts.UserName);

                        if (!string.IsNullOrWhiteSpace(rabbitOpts.Password))
                            h.Password(rabbitOpts.Password);
                    });

                cfg.ConfigureEndpoints(context);

                configureRabbitMq?.Invoke(cfg, context);
            });
        });
    }
}