# MassTransit & RabbitMQ Configuration

> This guide provides instructions for developers on how to set up and use MassTransit with RabbitMQ using dynamic
> configurations. The setup ensures a flexible and maintainable approach to configuring RabbitMQ exchanges, bindings,
> queues, etc., based on settings from a JSON file.

## Prerequisites

- .NET Core SDK
- RabbitMQ Server
- MassTransit Nuget packages (**Already Installed in the Infra Layer**)



## 1. Configure MassTransit In Micro
To use `MassTransit & RabbitMQ` in your micro project you should
to these steps:
- Add Reference to the MCAC.Infrastructure
- Add MassTransit Config Service In Your Micro Service Registration

`e.g: Identity Micro (Publishing Message)`
```csharp
namespace MCAC.Identity;

public class Startup
{
    public Startup(IConfiguration configuration)
    {
        Configuration = configuration;
    }

    public IConfiguration Configuration { get; }

    public void ConfigureServices(IServiceCollection services)
    {
        services.AddControllers();
        // for the send message and publish message
        services.AddMassTransitWithRabbitMq();
    }

    public void Configure(IApplicationBuilder app, IWebHostEnvironment env)
    {
        if (env.IsDevelopment())
        {
            app.UseDeveloperExceptionPage();
        }

        app.UseRouting();

        app.UseEndpoints(endpoints =>
        {
            endpoints.MapControllers();
        });
    }
}
```

`e.g: Branch Micro (Consume Message)`
```csharp
namespace MCAC.Branch;

public class Startup
{
    public Startup(IConfiguration configuration)
    {
        Configuration = configuration;
    }

    public IConfiguration Configuration { get; }

    public void ConfigureServices(IServiceCollection services)
    {
        services.AddControllers();
        
        // config MassTransit to consume massage
        services.AddMassTransitWithRabbitMq(
            // you can use this parameter to config the masstransit bus
            configureBus: (busConfig) =>
        {
            busConfig.AddConsumer<UserCreatedConsumer>();
        },
        // you can use this parameter to config the rabbitmq queue,exchange,bindings, etc ...
        configureRabbitMq: (cfg, context) =>
        {
            cfg.ReceiveEndpoint("user-created-queue", e =>
            {
                e.ConfigureConsumer<UserCreatedConsumer>(context);
            });
            
            // Additional RabbitMQ configuration for the BranchService
            cfg.Publish<UserCreated>(x =>
            {
                x.ExchangeType = "direct";
                x.Bind("user-exchange", s =>
                {
                    s.RoutingKey = "user-created";
                    s.ExchangeType = "direct";
                });
            });
        });
    }

    public void Configure(IApplicationBuilder app, IWebHostEnvironment env)
    {
        if (env.IsDevelopment())
        {
            app.UseDeveloperExceptionPage();
        }

        app.UseRouting();

        app.UseEndpoints(endpoints =>
        {
            endpoints.MapControllers();
        });
    }
}
```

