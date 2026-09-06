using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace CryptoSignal.Api.Migrations
{
    /// <inheritdoc />
    public partial class MarketScanner : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "Kind",
                table: "TradingBots",
                type: "integer",
                nullable: false,
                defaultValue: 0);

            migrationBuilder.AddColumn<string>(
                name: "StrategyKey",
                table: "TradingBots",
                type: "character varying(60)",
                maxLength: 60,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "SymbolsJson",
                table: "TradingBots",
                type: "character varying(2000)",
                maxLength: 2000,
                nullable: true);

            migrationBuilder.CreateTable(
                name: "ScannerSignals",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    ScanId = table.Column<Guid>(type: "uuid", nullable: false),
                    SignalCreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    Symbol = table.Column<string>(type: "character varying(30)", maxLength: 30, nullable: false),
                    Interval = table.Column<string>(type: "character varying(10)", maxLength: 10, nullable: false),
                    StrategyKey = table.Column<string>(type: "character varying(60)", maxLength: 60, nullable: false),
                    Direction = table.Column<int>(type: "integer", nullable: false),
                    Confidence = table.Column<double>(type: "double precision", nullable: false),
                    Score = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    AtrAtSignal = table.Column<decimal>(type: "numeric(28,10)", precision: 28, scale: 10, nullable: false),
                    Reason = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                    TakenByBotId = table.Column<Guid>(type: "uuid", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ScannerSignals", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ScannerSignals_TakenByBotId",
                table: "ScannerSignals",
                column: "TakenByBotId");

            migrationBuilder.CreateIndex(
                name: "IX_ScannerSignals_Symbol_Interval_Strategy_Claimed",
                table: "ScannerSignals",
                columns: new[] { "Symbol", "Interval", "StrategyKey", "TakenByBotId" });

            migrationBuilder.AddCheckConstraint(
                name: "CK_ScannerSignals_Confidence_InRange",
                table: "ScannerSignals",
                "\"Confidence\" >= 0.0 AND \"Confidence\" <= 1.0");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropCheckConstraint(
                name: "CK_ScannerSignals_Confidence_InRange",
                table: "ScannerSignals");

            migrationBuilder.DropTable(
                name: "ScannerSignals");

            migrationBuilder.DropColumn(name: "Kind", table: "TradingBots");
            migrationBuilder.DropColumn(name: "StrategyKey", table: "TradingBots");
            migrationBuilder.DropColumn(name: "SymbolsJson", table: "TradingBots");
        }
    }
}
