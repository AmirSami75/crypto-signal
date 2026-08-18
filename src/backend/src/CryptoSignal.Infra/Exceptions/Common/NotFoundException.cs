using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Abstract;

namespace CryptoSignal.Infra.Exceptions.Common;

public class NotFoundException : BaseException
{
    public NotFoundException() : base(
            errorCode: "NotFound",
            userMessage: "موردی یافت نشد",
            statusCode: ApiResultStatusCode.NotFound
        )
    {
    }

    public NotFoundException(string message) : base(
        errorCode: "NotFound",
        userMessage: message,
        statusCode: ApiResultStatusCode.NotFound
    )
    {
    }
}
