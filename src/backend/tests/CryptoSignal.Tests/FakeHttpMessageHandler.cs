using System.Net;
using System.Text;

namespace CryptoSignal.Tests;

/// <summary>
/// Captures outgoing <see cref="HttpRequestMessage"/>s and returns scripted responses keyed by the request
/// path (ignoring query string). Lets unit tests assert on the signed query the broker actually sent.
/// </summary>
public sealed class FakeHttpMessageHandler : HttpMessageHandler
{
    private readonly object _gate = new();
    private readonly List<HttpRequestMessage> _requests = [];

    /// <summary>Path (without query) -> response body + status.</summary>
    private readonly Dictionary<string, (HttpStatusCode Status, string Body)> _responses = new(
        StringComparer.OrdinalIgnoreCase);

    public IReadOnlyList<HttpRequestMessage> Requests
    {
        get
        {
            lock (_gate)
            {
                return _requests.ToList();
            }
        }
    }

    public void Respond(string path, HttpStatusCode status, string body) =>
        _responses[path] = (status, body);

    /// <summary>Make the next/the only send throw, to simulate transport timeouts/connection failures.</summary>
    public void Throw(Exception exception) => _throw = exception;

    private Exception? _throw;

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        lock (_gate)
        {
            _requests.Add(request);
        }

        if (_throw is { } ex)
            return Task.FromException<HttpResponseMessage>(ex);

        var path = request.RequestUri!.AbsolutePath;
        var (status, body) = _responses.TryGetValue(path, out var r)
            ? r
            : (HttpStatusCode.NotFound, "{\"code\":-1,\"msg\":\"no scripted response\"}");

        var response = new HttpResponseMessage(status)
        {
            Content = new StringContent(body, Encoding.UTF8, "application/json"),
        };
        return Task.FromResult(response);
    }
}
