namespace CryptoSignal.Auth.Application.DTOs.Auth;

public record TokenDto(string Token, DateTime ExpireDate);