using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Infra.Base.DB;

public abstract class BaseEntityTypeConfiguration<TEntity> : IEntityTypeConfiguration<TEntity>
    where TEntity : BaseEntity
{
    public virtual void Configure(EntityTypeBuilder<TEntity> builder)
    {
        // Stored as timestamptz; application code always writes UTC.
        builder.Property(e => e.CreatedAt)
            .IsRequired();

        builder.Property(e => e.IsDeleted)
            .IsRequired()
            .HasDefaultValue(false);

        // Concurrency token.
        // PostgreSQL has no rowversion type: map onto the xmin system column, which the
        // database bumps on every physical row update. There is no real column to create,
        // so this must never be treated as a mapped, writable property.
        builder.Property(e => e.RowVersion)
            .HasColumnName("xmin")
            .HasColumnType("xid")
            .ValueGeneratedOnAddOrUpdate()
            .IsConcurrencyToken();
    }
}
