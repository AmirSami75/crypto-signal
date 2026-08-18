namespace CryptoSignal.Infra.Attributes;

/// <summary>
/// این اتریبیوت برای مستند سازی در Swgger
/// و پیاده سازی سیستم سطوح دسترسی استفاده میشود
/// استفاده از آن در تمامی کنترلر ها الزامی است 
/// در صورت عدم استفاده سیستم سطوح دسترسی دچار اختلال می شود
/// </summary>
public class ControllerInfoAttribute : Attribute
{
    public string FullName { get; set; }
    public string Caption { get; private set; }

    public ControllerInfoAttribute(string fullName, string caption)
    {
        Caption = caption;
        FullName = fullName;
    }
}
