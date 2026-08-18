using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Abstract;

namespace CryptoSignal.Infra.Exceptions.Common;

public class LogicException : BaseException
{
    public LogicException(string? message = null, object? additionalData = null)
        : base(
            errorCode: "LogicError",
            userMessage: message ?? "A business logic error occurred.",
            statusCode: ApiResultStatusCode.ValidationError, // or use a custom status if you want (e.g. 422)
            additionalData: additionalData
        )
    { }
}
