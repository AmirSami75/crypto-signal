FROM mcr.microsoft.com/dotnet/sdk:10.0-noble AS build
WORKDIR /workspace

COPY contracts ./contracts
COPY src/backend/Directory.Build.props src/backend/CryptoMlSignal.slnx ./src/backend/
COPY src/backend/src/CryptoMlSignal.Api/CryptoMlSignal.Api.csproj \
    ./src/backend/src/CryptoMlSignal.Api/
RUN dotnet restore src/backend/CryptoMlSignal.slnx

COPY src/backend ./src/backend
RUN dotnet publish src/backend/src/CryptoMlSignal.Api/CryptoMlSignal.Api.csproj \
    --configuration Release \
    --output /app/publish \
    --no-restore

FROM mcr.microsoft.com/dotnet/sdk:10.0-noble AS development
WORKDIR /workspace/src/backend/src/CryptoMlSignal.Api
EXPOSE 8080

FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble AS runtime
WORKDIR /app
ENV ASPNETCORE_URLS=http://+:8080
COPY --from=build /app/publish .
USER app
EXPOSE 8080
ENTRYPOINT ["dotnet", "CryptoMlSignal.Api.dll"]
