using Asp.Versioning;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Api.Application.Security;
using CryptoSignal.Api.Domain.Enums.Trading;
using CryptoSignal.Api.Domain.Models.Trading;
using CryptoSignal.Auth.API.Attributes.Permissions;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Controller;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Base.DB.AuditUser;
using CryptoSignal.Infra.Base.Enums;
using Microsoft.AspNetCore.Mvc;

namespace CryptoSignal.Api.API.Controllers.v1.Trading;

/// <summary>One stored exchange connection as the API returns it.</summary>
/// <remarks>
/// There is deliberately no field here carrying either secret, encrypted or not: the ciphertext of a
/// key that can trade is itself sensitive material, and the dashboard has no use for it. The preview
/// tells the operator which row is which.
/// </remarks>
public sealed record ExchangeConnectionDto(
    Guid Id,
    MarketVenue Venue,
    string Label,
    string KeyPreview,
    bool IsActive,
    DateTime? LastValidatedAt,
    DateTime CreatedAt);

public sealed record ExchangeConnectionInput
{
    /// <summary>The venue these credentials speak to. Immutable after create — move the bots instead.</summary>
    public MarketVenue Venue { get; init; }

    public string Label { get; init; } = string.Empty;

    /// <summary>Write-only. Returned by no endpoint, in any form.</summary>
    public string ApiKey { get; init; } = string.Empty;

    /// <summary>Write-only. Sealed with AES-GCM before it touches the database.</summary>
    public string ApiSecret { get; init; } = string.Empty;
}

/// <summary>
/// CRUD over per-user exchange connections — where API keys live so a bot can trade a venue without
/// anything being configured on the server.
/// </summary>
[CustomAuthorize]
[ControllerInfo("ExchangeConnection", "اتصالات صرافی")]
public class ExchangeConnectionsController(
    IRepo<ExchangeConnection> connections,
    SecretProtector protector,
    ICurrentUserCtx currentUser) : BaseController
{
    [HttpGet]
    [Permission(PermissionType.Get)]
    public async Task<ApiResult<PagedResult<ExchangeConnectionDto>>> Get(
        CancellationToken ct,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 50)
    {
        var userId = RequireUser();

        pageNumber = Math.Max(1, pageNumber);
        pageSize = Math.Clamp(pageSize, 1, 200);

        var query = connections.TableNoTracking.Where(row => row.UserId == userId && !row.IsDeleted);

        var total = await query.CountAsync(ct);
        var items = await query
            .OrderByDescending(row => row.CreatedAt)
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .Select(row => new ExchangeConnectionDto(
                row.Id, row.Venue, row.Label, row.KeyPreview, row.IsActive,
                row.LastValidatedAt, row.CreatedAt))
            .ToListAsync(ct);

        return new PagedResult<ExchangeConnectionDto>(items, total, pageNumber, pageSize);
    }

    [HttpPost]
    [Permission(PermissionType.Create)]
    public async Task<ApiResult<Guid>> Create([FromBody] ExchangeConnectionInput input, CancellationToken ct)
    {
        var userId = RequireUser();
        ValidateSecrets(input);

        var connection = new ExchangeConnection
        {
            UserId = userId,
            Venue = input.Venue,
            Label = input.Label.Trim(),
            ApiKeyEncrypted = protector.Seal(input.ApiKey),
            ApiSecretEncrypted = protector.Seal(input.ApiSecret),
            KeyPreview = input.ApiKey.Length <= 4 ? input.ApiKey : input.ApiKey[^4..],
            IsActive = true,
        };

        await connections.AddAsync(connection, cancellationToken: ct);
        return connection.Id;
    }

    /// <summary>
    /// Replaces the credentials. Both secrets must arrive together: updating one half of a pair would
    /// leave a credential set that cannot sign anything, and the failure would surface at tick time
    /// rather than here where it can be refused.
    /// </summary>
    [HttpPut("{id:guid}")]
    [Permission(PermissionType.Update)]
    public async Task<ApiResult<bool>> Update(Guid id, [FromBody] ExchangeConnectionInput input, CancellationToken ct)
    {
        var userId = RequireUser();
        ValidateSecrets(input);

        var connection = await OwnedAsync(id, userId, ct)
                         ?? throw new KeyNotFoundException("این اتصال پیدا نشد");

        connection.Venue = input.Venue;
        connection.Label = input.Label.Trim();
        connection.ApiKeyEncrypted = protector.Seal(input.ApiKey);
        connection.ApiSecretEncrypted = protector.Seal(input.ApiSecret);
        connection.KeyPreview = input.ApiKey.Length <= 4 ? input.ApiKey : input.ApiKey[^4..];

        // A fresh key has not proven itself; the next successful venue round-trip re-stamps this.
        connection.LastValidatedAt = null;

        await connections.UpdateAsync(connection, cancellationToken: ct);
        return true;
    }

    /// <summary>Toggles <c>IsActive</c>. Deactivating makes the credential unresolvable immediately:
    /// every bot pinned to it faults on its next tick rather than trading with a revoked key.</summary>
    [HttpPost("{id:guid}/toggle-active")]
    [Permission(PermissionType.Custom, nameof(ToggleActive), "فعال یا غیرفعال کردن اتصال صرافی")]
    public async Task<ApiResult<bool>> ToggleActive(Guid id, CancellationToken ct)
    {
        var userId = RequireUser();

        var connection = await OwnedAsync(id, userId, ct)
                         ?? throw new KeyNotFoundException("این اتصال پیدا نشد");

        connection.IsActive = !connection.IsActive;
        await connections.UpdateAsync(connection, cancellationToken: ct);
        return connection.IsActive;
    }

    [HttpDelete("{id:guid}")]
    [Permission(PermissionType.Delete)]
    public async Task<ApiResult<bool>> Delete(Guid id, CancellationToken ct)
    {
        var userId = RequireUser();

        var connection = await OwnedAsync(id, userId, ct)
                         ?? throw new KeyNotFoundException("این اتصال پیدا نشد");

        await connections.SoftDeleteAsync(connection, cancellationToken: ct);
        return true;
    }

    private Guid RequireUser() =>
        currentUser.UserId
        ?? throw new UnauthorizedAccessException("این عملیات به ورود نیاز دارد");

    private Task<ExchangeConnection?> OwnedAsync(Guid id, Guid userId, CancellationToken ct) =>
        connections.TableNoTracking
            .Where(row => row.Id == id && row.UserId == userId && !row.IsDeleted)
            .FirstOrDefaultAsync(ct);

    private static void ValidateSecrets(ExchangeConnectionInput input)
    {
        if (string.IsNullOrWhiteSpace(input.ApiKey) || string.IsNullOrWhiteSpace(input.ApiSecret))
            throw new ArgumentException("کلید و مقدار مخفی API هر دو اجباری هستند");
    }
}
