using CryptoSignal.Infra.Base.Enums;

namespace CryptoSignal.Infra.Exceptions.Abstract;

public abstract class BaseException : Exception
{
    public string ErrorCode { get; set; }
    public ApiResultStatusCode StatusCode { get; set; }
    public string? UserMessage { get; set; }
    public object? AdditionalData { get; set; }


    protected BaseException(
        string errorCode,
        string? userMessage = null,
        ApiResultStatusCode statusCode = ApiResultStatusCode.ServerError,
        object? additionalData = null,
        Exception? innerException = null
    ) : base(userMessage, innerException)
    {
        ErrorCode = errorCode;
        StatusCode = statusCode;
        UserMessage = userMessage;
        AdditionalData = additionalData;
    }
}
