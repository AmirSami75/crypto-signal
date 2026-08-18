using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Reflection;
using CryptoSignal.Infra.Exceptions.Common;

namespace CryptoSignal.Infra.Extensions.Type;

public static class EnumExtensions
{
    public static IEnumerable<T> GetEnumValues<T>(this T input) where T : struct
    {
        if (!typeof(T).IsEnum)
            throw new NotSupportedException();

        return Enum.GetValues(input.GetType()).Cast<T>();
    }

    public static IEnumerable<T> GetEnumFlags<T>(this T input) where T : struct
    {
        if (!typeof(T).IsEnum)
            throw new NotSupportedException();

        foreach (var value in Enum.GetValues(input.GetType()))
            if ((input as Enum).HasFlag(value as Enum))
                yield return (T)value;
    }

    // Generic version avoids boxing and uses a safer member lookup
    public static string ToDisplay<TEnum>(
        this TEnum value,
        DisplayProperty property = DisplayProperty.Name)
        where TEnum : struct, Enum
    {
        var type = typeof(TEnum);

        // Use Enum.GetName -> Membership lookup is more reliable than GetField(value.ToString())
        var name = Enum.GetName(type, value);
        if (name is null)
            return value.ToString(); // fallback for undefined numeric values

        var member = type.GetMember(name).FirstOrDefault();
        if (member is null)
            return name;

        var attr = member.GetCustomAttribute<System.ComponentModel.DataAnnotations.DisplayAttribute>(inherit: false);
        if (attr is null)
            return name;

        // Use DisplayAttribute getters to support ResourceType-based localization
        return property switch
        {
            DisplayProperty.ShortName => attr.GetShortName() ?? name,
            DisplayProperty.Description => attr.GetDescription() ?? name,
            DisplayProperty.GroupName => attr.GetGroupName() ?? name,
            DisplayProperty.Prompt => attr.GetPrompt() ?? name,
            DisplayProperty.Order => attr.GetOrder()?.ToString() ?? name,
            _ => attr.GetName() ?? name,
        };
    }

    // If you need a non-generic signature:
    public static string ToDisplay(this Enum value, DisplayProperty property = DisplayProperty.Name)
    {
        var type = value.GetType();
        var name = Enum.GetName(type, value);
        if (name is null) return value.ToString();

        var member = type.GetMember(name).FirstOrDefault();
        if (member is null) return name;

        var attr = member.GetCustomAttribute<System.ComponentModel.DataAnnotations.DisplayAttribute>(inherit: false);
        if (attr is null) return name;

        return property switch
        {
            DisplayProperty.ShortName => attr.GetShortName() ?? name,
            DisplayProperty.Description => attr.GetDescription() ?? name,
            DisplayProperty.GroupName => attr.GetGroupName() ?? name,
            DisplayProperty.Prompt => attr.GetPrompt() ?? name,
            DisplayProperty.Order => attr.GetOrder()?.ToString() ?? name,
            _ => attr.GetName() ?? name,
        };
    }

    public static string GetDescription(this Enum value)
    {
        FieldInfo field = value.GetType().GetField(value.ToString());

        if (field != null)
        {
            DescriptionAttribute[] attributes = (DescriptionAttribute[])field.GetCustomAttributes(
                typeof(DescriptionAttribute),
                false
            );

            if (attributes != null && attributes.Length > 0)
            {
                return attributes[0].Description;
            }
        }

        return value.ToString();
    }

    public static T? FromString<T>(string value) where T : struct, Enum
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;

        if (Enum.TryParse(typeof(T), value, true, out var result))
        {
            return (T)result;
        }

        return null;
    }
}

public enum DisplayProperty
{
    Description,
    GroupName,
    Name,
    Prompt,
    ShortName,
    Order
}