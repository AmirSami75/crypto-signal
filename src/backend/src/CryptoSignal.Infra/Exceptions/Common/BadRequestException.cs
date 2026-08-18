using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Abstract;

namespace CryptoSignal.Infra.Exceptions.Common;

public class BadRequestException : BaseException
{
    public BadRequestException(string? message = null)
    : base(
        errorCode: "BadRequest",
        userMessage: message ?? "Invalid request.",
        statusCode: ApiResultStatusCode.BadRequest
    )
    { }
}
