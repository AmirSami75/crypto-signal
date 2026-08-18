using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Abstract;

namespace CryptoSignal.Infra.Exceptions.Common;

public class UnauthorizedException : BaseException
{
    public UnauthorizedException(string? message = null, Exception ex = null)
        : base(
            errorCode: "Unauthorized",
            userMessage: message ?? "سطح دسترسی شما مجاز نیست.",
            statusCode: ApiResultStatusCode.Unauthorized
        )
    { }
}
