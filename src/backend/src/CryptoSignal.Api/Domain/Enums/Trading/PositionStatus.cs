using System.ComponentModel.DataAnnotations;

namespace CryptoSignal.Api.Domain.Enums.Trading;

/// <summary>Whether a position still has exposure.</summary>
public enum PositionStatus
{
    [Display(Name = "Open")] Open = 1,
    [Display(Name = "Closed")] Closed = 2,
}
