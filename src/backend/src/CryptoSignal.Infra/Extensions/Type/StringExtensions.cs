using System.Text.RegularExpressions;

namespace CryptoSignal.Infra.Extensions.Type;

public static class StringExtensions
{
    public static string ToCapitalize(this string value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return value;
        }

        if (value.Length == 1)
            return value.ToUpper();
        else
            return char.ToUpper(value[0]) + value.Substring(1, value.Length - 1);
    }

    public static bool HasValue(this string value, bool ignoreWhiteSpace = true)
    {
        return ignoreWhiteSpace ? !string.IsNullOrWhiteSpace(value) : !string.IsNullOrEmpty(value);
    }

    public static int ToInt(this string value)
    {
        return Convert.ToInt32(value);
    }

    public static decimal ToDecimal(this string value)
    {
        return Convert.ToDecimal(value);
    }

    public static string ToNumeric(this int value)
    {
        return value.ToString("N0"); //"123,456"
    }

    public static string ToNumeric(this decimal value)
    {
        return value.ToString("N0");
    }

    public static string ToCurrency(this int value)
    {
        //fa-IR => current culture currency symbol => ریال
        //123456 => "123,123ریال"
        return value.ToString("C0");
    }

    public static string ToCurrency(this decimal value)
    {
        return value.ToString("C0");
    }

    public static string En2Fa(this string str)
    {
        return str.Replace("0", "۰")
            .Replace("1", "۱")
            .Replace("2", "۲")
            .Replace("3", "۳")
            .Replace("4", "۴")
            .Replace("5", "۵")
            .Replace("6", "۶")
            .Replace("7", "۷")
            .Replace("8", "۸")
            .Replace("9", "۹");
    }

    public static string Fa2En(this string str)
    {
        return str.Replace("۰", "0")
            .Replace("۱", "1")
            .Replace("۲", "2")
            .Replace("۳", "3")
            .Replace("۴", "4")
            .Replace("۵", "5")
            .Replace("۶", "6")
            .Replace("۷", "7")
            .Replace("۸", "8")
            .Replace("۹", "9")
            .Replace("٠", "0")
            .Replace("١", "1")
            .Replace("٢", "2")
            .Replace("٣", "3")
            .Replace("٤", "4")
            .Replace("٥", "5")
            .Replace("٦", "6")
            .Replace("٧", "7")
            .Replace("٨", "8")
            .Replace("٩", "9");
    }

    public static string FixPersianChars(this string str)
    {
        return str
            .Replace("ﮎ", "ک")
            .Replace("ﮏ", "ک")
            .Replace("ﮐ", "ک")
            .Replace("ﮑ", "ک")
            .Replace("ك", "ک")
            .Replace("ي", "ی")
            .Replace("ئ", "ی")
            .Replace(" ", " ")
            .Replace("‌", " ")
            .Replace("ھ", "ه");
    }

    public static string? CleanString(this string str)
    {
        return str.Trim().FixPersianChars().Fa2En().NullIfEmpty();
    }

    public static string? NullIfEmpty(this string str)
    {
        return str?.Length == 0 ? null : str;
    }

    public static bool IsValidMobile(this string mobile)
    {
        var r = new Regex(@"^(?:0|98|\+98|\+980|0098|098|00980)?(9\d{9})$");
        return r.IsMatch(mobile);
    }

    public static bool IsValidEmail(this string email)
    {
        string patternStrict = @"^(([^<>()[\]\\.,;:\s@\""]+"
                               + @"(\.[^<>()[\]\\.,;:\s@\""]+)*)|(\"".+\""))@"
                               + @"((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"
                               + @"\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+"
                               + @"[a-zA-Z]{2,}))$";
        Regex reStrict = new System.Text.RegularExpressions.Regex(patternStrict);
        bool isStrictMatch = reStrict.IsMatch(email);
        return isStrictMatch;
    }

    public static bool IsValidPhone(this string phone)
    {
        var r = new Regex(@"^0[0-9]{2,}[0-9]{7,}$");
        return r.IsMatch(phone);
    }

    public static bool IsValidPersonalCode(this string personalCode)
    {
        return new Regex(@"\d+").IsMatch(personalCode);
    }

    public static bool IsStrongPassword(this string password)
    {
        HashSet<char> specialCharacters = new HashSet<char>()
            { '!', '%', '$', '#', '@', '&', '*', '(', ')', '-', '_', '+', '=', '~', '|', ',', '<', '.', '>', '?', '/' };
        int conditionsCount = 0;
        if (password.Length >= 8)
            conditionsCount++;
        if (password.Any(char.IsLower))
            conditionsCount++;
        if (password.Any(char.IsUpper))
            conditionsCount++;
        if (password.Any(char.IsDigit))
            conditionsCount++;
        if (password.Any(specialCharacters.Contains))
            conditionsCount++;

        if (conditionsCount == 5)
            return true;
        return false;
    }
}