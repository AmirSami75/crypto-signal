namespace CryptoSignal.Infra.Base.Enums;

public enum DateFormat
{
    DateOnly, // e.g., "yyyy/MM/dd"
    TimeOnly, // e.g., "HH:mm:ss"
    DateTime, // e.g., "yyyy/MM/dd HH:mm:ss"
    IsoDateTime, // e.g, "yyyy-MM-ddTHH:mm:ss"
    DateWith2DigitYears, // e.g., "yy/MM/dd"
}