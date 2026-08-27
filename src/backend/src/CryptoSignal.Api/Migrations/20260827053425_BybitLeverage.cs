using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace CryptoSignal.Api.Migrations
{
    /// <inheritdoc />
    public partial class BybitLeverage : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "Leverage",
                table: "TradingBots",
                type: "integer",
                nullable: false,
                defaultValue: 1);

            migrationBuilder.AddColumn<int>(
                name: "Leverage",
                table: "OrderIntents",
                type: "integer",
                nullable: false,
                defaultValue: 1);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Leverage",
                table: "TradingBots");

            migrationBuilder.DropColumn(
                name: "Leverage",
                table: "OrderIntents");
        }
    }
}
