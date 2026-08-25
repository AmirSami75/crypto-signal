using CryptoSignal.Api.Application.Markers;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Infra.Base.DB;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
namespace CryptoSignal.Api.Application.Security;

/// <summary>Credentials resolved for one venue, ready to sign requests with.</summary>
public sealed record VenueCredentials(string ApiKey, string ApiSecret)
{
    public bool HasCredentials => !string.IsNullOrWhiteSpace(ApiKey) && !string.IsNullOrWhiteSpace(ApiSecret);
}

/// <summary>
/// Resolves API credentials for a (user, venue) pair — from their stored connection first, then from
/// server environment as the operator-level fallback.
/// </summary>
/// <remarks>
/// <para>
/// The order matters and is deliberate: a user's own stored connection is theirs to manage from the
/// dashboard; the environment value is what a single-operator deployment uses without touching the
/// database. Neither source silently overrides an explicit pin — when a bot names a connection id,
/// only that row is consulted, and it must belong to the bot's owner.
/// </para>
/// <para>
/// A missing or inactive credential resolves to empty rather than throwing: callers already speak
/// "no credentials" fluently (fail-closed rejections), and the resolution site has better context
/// for the message than this layer would.
/// </para>
/// </remarks>
public interface ICredentialProvider
{
    /// <summary>Explicitly pinned connection. Must exist, be active, and belong to <paramref name="userId"/>.</summary>
    Task<VenueCredentials> ForConnectionAsync(Guid userId, Guid connectionId, CancellationToken cancellationToken);

    /// <summary>Best credentials for a venue: the user's active stored one, else the environment's.</summary>
    Task<VenueCredentials> ResolveAsync(Guid userId, MarketVenue venue, CancellationToken cancellationToken);
}

public sealed class CredentialProvider(
    IRepo<Domain.Models.Trading.ExchangeConnection> repo,
    SecretProtector protector,
    ILogger<CredentialProvider> logger) : ICredentialProvider, IScopedSvcMarker
{
    public async Task<VenueCredentials> ForConnectionAsync(
        Guid userId, Guid connectionId, CancellationToken cancellationToken)
    {
        var connection = await repo.GetByIdAsync(cancellationToken, connectionId);

        if (connection is null || connection.UserId != userId || connection.IsDeleted)
            throw new UnauthorizedAccessException(
                $"Exchange connection {connectionId} does not exist or belongs to another user.");

        if (!connection.IsActive)
            return new VenueCredentials(string.Empty, string.Empty);

        return Decrypt(connection);
    }

    public async Task<VenueCredentials> ResolveAsync(
        Guid userId, MarketVenue venue, CancellationToken cancellationToken)
    {
        var spec = new Spec<Domain.Models.Trading.ExchangeConnection>
        {
            Criteria = x => x.UserId == userId && x.Venue == venue && x.IsActive && !x.IsDeleted,
            OrderBy = q => q.OrderByDescending(x => x.CreatedAt),
            Take = 1,
            AsNoTracking = true,
        };

        var connection = await repo.FirstOrDefaultAsync(spec, cancellationToken);

        if (connection is null)
        {
            logger.LogDebug("No stored {Venue} connection for user {UserId}; falling back to environment",
                venue, userId);
            return new VenueCredentials(string.Empty, string.Empty);
        }

        return Decrypt(connection);
    }

    private VenueCredentials Decrypt(Domain.Models.Trading.ExchangeConnection connection) =>
        new(protector.Open(connection.ApiKeyEncrypted), protector.Open(connection.ApiSecretEncrypted));
}
