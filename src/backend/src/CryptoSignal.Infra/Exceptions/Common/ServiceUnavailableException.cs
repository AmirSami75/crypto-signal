using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Abstract;

namespace CryptoSignal.Infra.Exceptions.Common;

public class ServiceUnavailableException : BaseException
{
    public ServiceUnavailableException(string? message = null)
         : base(
             errorCode: "ServiceUnavailable",
             userMessage: message ?? "The service is temporarily unavailable. Please try again later.",
             statusCode: ApiResultStatusCode.ServiceUnavailable
         )
    { }
}
