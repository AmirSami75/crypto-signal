using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Auth.Application.DTOs.Auth;

public abstract record BaseLoginDto(string UserName, string Password);