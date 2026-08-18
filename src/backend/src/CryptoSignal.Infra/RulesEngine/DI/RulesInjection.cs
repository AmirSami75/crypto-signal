using System.Reflection;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using CryptoSignal.Infra.RulesEngine.Contracts;
using CryptoSignal.Infra.RulesEngine.Implementations;

namespace CryptoSignal.Infra.RulesEngine.DI;

public static class RulesInjection
{
    public static IServiceCollection AddRuleEngines(this IServiceCollection services, params Assembly[] ruleAssemblies)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(ruleAssemblies);

        var assemblies = ruleAssemblies
            .Where(assembly => assembly is not null)
            .Distinct()
            .ToArray();
        
        if (assemblies.Length == 0)
        {
            throw new ArgumentException(
                "At least one rule assembly must be provided.",
                nameof(ruleAssemblies));
        }

        services.TryAddScoped(
            typeof(IRuleEngine<>),
            typeof(RuleEngine<>));

        services.TryAddScoped(
            typeof(ICrudRuleExecutor<,,>),
            typeof(CrudRuleExecutor<,,>));
        
        services.Scan(scan => scan
            .FromAssemblies(assemblies)
            .AddClasses(classes =>
                classes.AssignableTo(typeof(IRule<>)))
            .AsImplementedInterfaces()
            .WithScopedLifetime());

        return services;
    }
}