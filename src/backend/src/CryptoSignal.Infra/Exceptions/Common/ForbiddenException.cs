using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Abstract;

namespace CryptoSignal.Infra.Exceptions.Common;

public class ForbiddenException : BaseException
{
    public ForbiddenException(string? message = null)
        : base(
            errorCode: "Forbidden",
            userMessage: message ?? "You do not have permission to perform this action.",
            statusCode: ApiResultStatusCode.Forbidden
        )
    { }
}
