using CryptoSignal.Infra.Base.Enums;

namespace CryptoSignal.Infra.Attributes;

public class PermissionAttribute : Attribute
{
    public string ActionName { get; private set; }

    public string ActionCaption { get; private set; }

    public PermissionType Type { get; private set; }

    public PermissionAttribute(PermissionType type, string actionName = "", string actionCaption = "")
    {
        Type = type;
        ActionCaption = actionCaption;
        ActionName = actionName;
        switch (type)
        {
            case PermissionType.Get:
                ActionCaption = "دریافت اطلاعات {0}";
                ActionName = type.ToString();
                break;
            case PermissionType.Create:
                ActionCaption = "افزودن {0} جدید";
                ActionName = type.ToString();
                break;
            case PermissionType.Update:
                ActionCaption = "ویرایش {0}";
                ActionName = type.ToString();
                break;
            case PermissionType.Delete:
                ActionCaption = "حذف {0}";
                ActionName = type.ToString();
                break;
            case PermissionType.Custom:
            default:
                break;
        }
    }
}
