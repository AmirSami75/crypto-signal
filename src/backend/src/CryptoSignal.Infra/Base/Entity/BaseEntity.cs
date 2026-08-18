using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using Microsoft.EntityFrameworkCore;

namespace CryptoSignal.Infra.Base.Entity;

public interface IEntityMarker
{
    bool IsDeleted { get; set; }

    /// <summary>
    /// Optimistic-concurrency token. Mapped to the PostgreSQL <c>xmin</c> system column,
    /// so it is maintained by the database and never assigned by application code.
    /// </summary>
    uint RowVersion { get; set; }

    DateTime CreatedAt { get; }
    DateTime? UpdatedAt { get; }
}

public abstract class BaseEntity : BaseEntity<Guid>
{
}

public abstract class BaseEntity<T> : IEntityMarker
    where T : struct
{
    public T Id { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public DateTime? UpdatedAt { get; set; }

    public bool IsDeleted { get; set; }

    /// <summary>
    /// Mapped to the PostgreSQL <c>xmin</c> system column by
    /// <see cref="CryptoSignal.Infra.Base.DB.BaseEntityTypeConfiguration{TEntity}"/>.
    /// Database-generated; do not set from application code.
    /// </summary>
    public uint RowVersion { get; set; }
    
    public T? UserCreatedId { get; set; }

    public string? UserCreatedName { get; set; }

    public T? UserLastUpdatedId { get; set; }

    public string? UserLastUpdateName { get; set; }
    

    public override bool Equals(object? obj)
    {
        if (obj is not BaseEntity<T> other) return false;
        if (ReferenceEquals(this, other)) return true;
        return Id.Equals(other.Id);
    }

    public static bool operator ==(BaseEntity<T>? left, BaseEntity<T>? right)
    {
        if (left is null && right is null) return true;
        if (left is null || right is null) return false;
        return left.Equals(right);
    }

    public static bool operator !=(BaseEntity<T>? left, BaseEntity<T>? right) => !(left == right);

    public override int GetHashCode() => Id.GetHashCode();

    public override string ToString() => $"{GetType().Name} [Id={Id}]";
}