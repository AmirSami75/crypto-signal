namespace CryptoSignal.Infra.Base.DB;

public interface IEntitySeedData
{
    int Order { get; }
    Task SeedAsync();
}