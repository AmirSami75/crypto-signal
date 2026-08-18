using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Abstract;

namespace CryptoSignal.Infra.Exceptions.Common;

public class ValidationException : BaseException
{
    public ValidationException(object errors)
        : base(
            errorCode: "ValidationError",
            userMessage: "Validation failed.",
            statusCode: ApiResultStatusCode.ValidationError,
            additionalData: errors
        )
    { }
}
