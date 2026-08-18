using Microsoft.AspNetCore.Mvc;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Base.Enums;
using System.Reflection;

namespace CryptoSignal.Auth.Adapter.Presistence.Seeders;

public sealed class PermissionSeeder(IPermissionRepo repo) : IEntitySeedData
{
    public int Order => 3;

    public async Task SeedAsync()
    {
        Console.WriteLine("Start seed permission data.");
        var entryAssembly = Assembly.GetEntryAssembly();
        if (entryAssembly != null)
        {
            List<Assembly> source = [entryAssembly];

            var loadedAssemblies = entryAssembly?
                .GetReferencedAssemblies()
                .Where(p => p.Name!.Contains("CryptoSignal"))
                .Select(Assembly.Load)
                .ToList();
            if (loadedAssemblies != null)
            {
                loadedAssemblies.ForEach(source.Add);

                foreach (var item in source)
                {
                    Console.WriteLine($"Assembly name : {item.FullName}");
                    var controllers = GetChildTypes<BaseController>(item);
                    Console.WriteLine($"Controllers counts : {controllers.Count()}");
                    foreach (var controller in controllers)
                    {
                        Console.WriteLine($"Contoller name : {controller.Name}");
                        IEnumerable<MethodInfo> actions = null;

                        List<(string name, string title, PermissionType type)> permissions =
                            new List<(string name, string title, PermissionType type)>();

                        var controllerInfo = controller.GetCustomAttribute<ControllerInfoAttribute>();

                        if (controllerInfo != null)
                        {
                            actions = controller.GetMethods()
                                //.Where(p => p.DeclaringType.Name == controller.Name || p.DeclaringType.BaseType?.Name == "CrudController" || p.DeclaringType.BaseType?.Name == "BaseController")
                                .Where(p => p.GetCustomAttribute(typeof(PermissionAttribute)) != null)
                                .Where(p => p.GetCustomAttribute<NonActionAttribute>() == null)
                                .ToList();

                            foreach (var action in actions)
                            {
                                var permissionName = string.Empty;
                                var permissionCaption = string.Empty;
                                var attr =
                                    (action.GetCustomAttribute(typeof(PermissionAttribute)) as PermissionAttribute);
                                if (attr != null)
                                {
                                    if (attr.Type == PermissionType.Custom)
                                    {
                                        permissionName = $"{controllerInfo.FullName}.{attr?.ActionName}";
                                        permissionCaption = attr?.ActionCaption;
                                    }
                                    else
                                    {
                                        permissionName = $"{controllerInfo.FullName}.{attr?.Type}";
                                        permissionCaption = string.Format(attr?.ActionCaption, controllerInfo.Caption);
                                    }

                                    if (!permissions.Any(p => p.name.Contains(permissionName)))
                                    {
                                        permissions.Add((permissionName, permissionCaption, attr.Type));
                                    }
                                }
                            }

                            foreach (var permission in permissions)
                            {
                                if (!repo.TableNoTracking.Any(p => p.Name == permission.name))
                                {
                                    await repo.AddAsync(new Permission
                                    {
                                        Name = permission.name,
                                        Title = permission.title,
                                        Type = permission.type,
                                    });
                                }
                            }
                        }
                    }
                }

                Console.WriteLine("End seed permission data.");
            }
            else
            {
                Console.WriteLine("LoadedAssemblies is null");
            }
        }
        else
        {
            Console.WriteLine("EntryAssembly is null");
        }
    }

    private IEnumerable<Type> GetChildTypes<T>(Assembly apiAssembly)
    {
        var types = apiAssembly?.GetTypes();
        return types?.Where(t => t.IsSubclassOf(typeof(T)) && !t.IsAbstract && t.IsPublic);
    }
}