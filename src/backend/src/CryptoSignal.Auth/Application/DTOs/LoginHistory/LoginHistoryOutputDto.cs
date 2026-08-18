using Mapster;
using CryptoSignal.Infra.Base.API.DTO;
using CryptoSignal.Infra.Extensions.Type;

namespace CryptoSignal.Auth.Application.DTOs.LoginHistory;

public class LoginHistoryOutputDto :
    BaseOutputDto<Domain.Models.LoginHistory, LoginHistoryOutputDto, Guid>
{
    public string Ip { get; set; }

    public string UserAgent { get; set; }

    public string DateTime { get; set; }

    public string Status { get; set; }

    public override void Register(TypeAdapterConfig config)
    {
        base.Register(config);
        config.ForType<LoginHistoryOutputDto, LoginHistoryOutputDto>()
            .AfterMapping((src, dest) =>
            {
                dest.DateTime = src.CreatedAtRaw.ConvertToPersianDate();
            });
    }
}