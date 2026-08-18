FROM mcr.microsoft.com/dotnet/sdk:10.0-noble AS build
WORKDIR /workspace

# Protos are compiled by Grpc.Tools during build; the Api csproj links them from ../../../../contracts.
COPY contracts ./contracts

# Restore against the project files alone so the NuGet layer is reused whenever only sources change.
COPY src/backend/global.json src/backend/Directory.Build.props src/backend/CryptoSignal.slnx ./src/backend/
COPY src/backend/src/CryptoSignal.Infra/CryptoSignal.Infra.csproj ./src/backend/src/CryptoSignal.Infra/
COPY src/backend/src/CryptoSignal.Auth/CryptoSignal.Auth.csproj ./src/backend/src/CryptoSignal.Auth/
COPY src/backend/src/CryptoSignal.Api/CryptoSignal.Api.csproj ./src/backend/src/CryptoSignal.Api/
RUN dotnet restore src/backend/CryptoSignal.slnx

COPY src/backend ./src/backend
RUN dotnet publish src/backend/src/CryptoSignal.Api/CryptoSignal.Api.csproj \
    --configuration Release \
    --output /app/publish \
    --no-restore

FROM mcr.microsoft.com/dotnet/sdk:10.0-noble AS development
WORKDIR /workspace/src/backend/src/CryptoSignal.Api
EXPOSE 8080

FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble AS runtime
WORKDIR /app
ENV ASPNETCORE_URLS=http://+:8080
COPY --from=build /app/publish .
USER app
EXPOSE 8080
ENTRYPOINT ["dotnet", "CryptoSignal.Api.dll"]
