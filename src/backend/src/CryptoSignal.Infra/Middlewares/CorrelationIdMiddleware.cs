using Microsoft.AspNetCore.Http;

namespace CryptoSignal.Infra.Middlewares;

/// <summary>
/// Attaches a correlation id to every request and echoes it back.
///
/// When something goes wrong in production the first question is always "which log lines belong to
/// this failure?" — without an id that travels client → API → ML engine, answering it means
/// eyeballing timestamps across services. The id is accepted from <c>X-Correlation-Id</c> (a proxy
/// may already have chosen one) and minted as a GUID when absent. It lands in the response header
/// so a support conversation can start from the user's failed request, not from guesswork.
///
/// Log correlation itself comes free: Serilog's request logging includes this header via the
/// diagnostics context, and the tick executor already threads its own correlation ids into audit
/// events with the same intent.
/// </summary>
public sealed class CorrelationIdMiddleware(RequestDelegate next)
{
    public const string HeaderName = "X-Correlation-Id";

    public async Task InvokeAsync(HttpContext context)
    {
        var correlationId = context.Request.Headers.TryGetValue(HeaderName, out var provided)
                            && !string.IsNullOrWhiteSpace(provided)
            ? provided.ToString()
            : Guid.NewGuid().ToString("n");

        context.Items[HeaderName] = correlationId;
        context.Response.Headers[HeaderName] = correlationId;

        // Serilog enrichers read this property; LogContext pushes it onto every line logged inside
        // the request, so a grep for the id returns the whole story of one failed call.
        using (Serilog.Context.LogContext.PushProperty("CorrelationId", correlationId))
        {
            await next(context);
        }
    }
}
