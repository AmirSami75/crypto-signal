using System.ComponentModel.DataAnnotations.Schema;
using CryptoSignal.Auth.Domain.Enums;
using CryptoSignal.Infra.Base.Entity;

namespace CryptoSignal.Auth.Domain.Models;

public class LoginHistory : BaseEntity
{
    #region Properties

    public Guid UserId { get; set; }

    public string? Ip { get; set; }

    public string? UserAgent { get; set; }

    public LoginStatus Status { get; set; }

    public LoginType LoginType { get; set; } = LoginType.Internal;

    #endregion

    #region Navigation Properties

    [ForeignKey(nameof(UserId))] public BaseUser BaseUser { get; set; }

    #endregion
}