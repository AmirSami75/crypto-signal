using System.Globalization;
using CryptoSignal.Infra.Base.Enums;

namespace CryptoSignal.Infra.Extensions.Type;

public static class DateTimeExtensions
{
    public static string ConvertToPersianDate(
        this DateTime gregorianDateTime,
        DateFormat format = DateFormat.DateTime,
        string timeSeparator = ":",
        string dateSeparator = "/",
        bool includeMilliseconds = false)
    {
        try
        {
            var persianCalendar = new PersianCalendar();
            var year = persianCalendar.GetYear(gregorianDateTime);
            var month = persianCalendar.GetMonth(gregorianDateTime);
            var day = persianCalendar.GetDayOfMonth(gregorianDateTime);
            var hour = persianCalendar.GetHour(gregorianDateTime);
            var minute = persianCalendar.GetMinute(gregorianDateTime);
            var second = persianCalendar.GetSecond(gregorianDateTime);
            var ms = persianCalendar.GetMilliseconds(gregorianDateTime);

            var persianDate = $"{year}{dateSeparator}{month:00}{dateSeparator}{day:00}";
            var persianTime = $"{hour:00}{timeSeparator}{minute:00}{timeSeparator}{second:00}";

            return format switch
            {
                DateFormat.DateOnly => persianDate,
                DateFormat.TimeOnly => includeMilliseconds ? $"{persianTime}{ms}" : persianTime,
                DateFormat.DateTime => $"{persianDate} {persianTime}",
                DateFormat.IsoDateTime => $"{persianDate}T{persianTime}",
                DateFormat.DateWith2DigitYears =>
                    $"{year % 100:00}{dateSeparator}{month:00}{dateSeparator}{day:00}",
                _ => $"{persianDate} {persianTime}",
            };
        }
        catch
        {
            return string.Empty;
        }
    }

    public static string FormatCompactPersianDate(this string compactDate)
    {
        if (string.IsNullOrWhiteSpace(compactDate))
            return compactDate;
        
        // Handle different input formats
        var cleanDate = new string(compactDate.Where(char.IsDigit).ToArray());
        
        return cleanDate.Length switch
        {
            8 => $"{cleanDate[..4]}/{cleanDate.Substring(4, 2)}/{cleanDate.Substring(6, 2)}",
            6 => $"{cleanDate[..4]}/{cleanDate.Substring(4, 2)}/01", // Year and month only
            _ => compactDate
        };
    }
    
    public static DateTime ConvertToGregorianDate(
        this string persianDate,
        char dateSeparator = '/',
        int hour = 0,
        int minute = 0,
        int second = 0)
    {
        if (string.IsNullOrWhiteSpace(persianDate))
            throw new ArgumentNullException(nameof(persianDate));

        try
        {
            string[] dateTimeParts = persianDate.Split(' ');
            string[] dateParts = dateTimeParts[0].Split(dateSeparator);

            int year = int.Parse(dateParts[0]);
            int month = int.Parse(dateParts[1]);
            int day = int.Parse(dateParts[2]);

            var pc = new PersianCalendar();

            var miladiDateTime =
                pc.ToDateTime(year, month, day, hour, minute, second, 0, PersianCalendar.PersianEra);

            return miladiDateTime;
        }
        catch (Exception)
        {
            return DateTime.Now;
        }
    }

    public static string ConvertToGregorianDate(this string persianDate, string format)
    {
        string trimmedDate = persianDate.Trim();
        var result = DateTime.MinValue;
        try
        {
            string[]? timeParts = default;
            string[]? dateParts = default;
            string[] dateTimeParts = persianDate.Split(' ');
            if (dateTimeParts.Length > 1)
            {
                timeParts = dateTimeParts[1].Split(':');
            }

            dateParts = dateTimeParts[0].Split('/');
            int year = int.Parse(dateParts[0]);
            int month = int.Parse(dateParts[1]);
            int day = int.Parse(dateParts[2]);
            int h = 0;
            int m = 0;
            int s = 0;
            if (timeParts?.Length == 3)
            {
                h = int.Parse(timeParts[0]);
                m = int.Parse(timeParts[1]);
                s = int.Parse(timeParts[2]);
            }

            PersianCalendar persianCalendar = new PersianCalendar();
            DateTime miladiDate = persianCalendar.ToDateTime(year, month, day, h, m, s, 0);
            return miladiDate.ToString(format).Split(" ")[0];
        }
        catch
        {
            throw;
        }
    }

    public static bool IsValidPersianDate(this string persianDate, out DateTime gregorianDate)
    {
        gregorianDate = ConvertToGregorianDate(persianDate);
        return gregorianDate != DateTime.MinValue;
    }
    
        // =========================
    // Fiscal Year (Persian)
    // =========================

    /// <summary>
    /// Returns the Persian fiscal year number for a Gregorian DateTime, based on Persian calendar month.
    /// Default fiscal year start is Farvardin (1).
    /// Example: if startMonth=1, 1401/01/01 => 1401
    /// </summary>
    public static int GetPersianFiscalYear(this DateTime gregorianDate, int fiscalYearStartMonth = 1)
    {
        if (fiscalYearStartMonth < 1 || fiscalYearStartMonth > 12)
            throw new ArgumentOutOfRangeException(nameof(fiscalYearStartMonth), "Must be between 1 and 12.");

        var pc = new PersianCalendar();
        var pYear = pc.GetYear(gregorianDate);
        var pMonth = pc.GetMonth(gregorianDate);

        return pMonth < fiscalYearStartMonth ? pYear - 1 : pYear;
    }

    /// <summary>
    /// Returns the Persian fiscal year number for a Persian date string like "1401/01/01".
    /// </summary>
    public static int GetPersianFiscalYear(this string persianDate, int fiscalYearStartMonth = 1, char dateSeparator = '/')
    {
        if (string.IsNullOrWhiteSpace(persianDate))
            throw new ArgumentNullException(nameof(persianDate));

        var dateOnly = persianDate.Split(' ')[0];
        var parts = dateOnly.Split(dateSeparator);

        var year = int.Parse(parts[0]);
        var month = int.Parse(parts[1]);

        if (fiscalYearStartMonth < 1 || fiscalYearStartMonth > 12)
            throw new ArgumentOutOfRangeException(nameof(fiscalYearStartMonth), "Must be between 1 and 12.");

        return month < fiscalYearStartMonth ? year - 1 : year;
    }

    /// <summary>
    /// Returns a label like "1401-1402" for the fiscal year of the given date (Persian calendar).
    /// </summary>
    public static string GetPersianFiscalYearLabel(this DateTime gregorianDate, int fiscalYearStartMonth = 1, string separator = "-")
    {
        var fy = gregorianDate.GetPersianFiscalYear(fiscalYearStartMonth);
        return $"{fy}{separator}{fy + 1}";
    }

    /// <summary>
    /// Returns the fiscal year range label based on a from/to Persian date (e.g. "1401-1402").
    /// Uses fromDate as the anchor (common approach).
    /// </summary>
    public static string GetPersianFiscalYearLabel(this string fromPersianDate, string toPersianDate, int fiscalYearStartMonth = 1, string separator = "-")
    {
        // Anchor on from-date fiscal year (typical in reporting)
        var fy = fromPersianDate.GetPersianFiscalYear(fiscalYearStartMonth);
        return $"{fy}{separator}{fy + 1}";
    }
}
