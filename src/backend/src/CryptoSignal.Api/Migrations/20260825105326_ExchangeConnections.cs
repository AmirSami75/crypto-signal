using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace CryptoSignal.Api.Migrations
{
    /// <inheritdoc />
    public partial class ExchangeConnections : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<Guid>(
                name: "ExchangeConnectionId",
                table: "TradingBots",
                type: "uuid",
                nullable: true);

            migrationBuilder.CreateTable(
                name: "ExchangeConnections",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    Venue = table.Column<int>(type: "integer", nullable: false),
                    Label = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    ApiKeyEncrypted = table.Column<string>(type: "character varying(512)", unicode: false, maxLength: 512, nullable: false),
                    ApiSecretEncrypted = table.Column<string>(type: "character varying(512)", unicode: false, maxLength: 512, nullable: false),
                    KeyPreview = table.Column<string>(type: "character varying(8)", unicode: false, maxLength: 8, nullable: false),
                    IsActive = table.Column<bool>(type: "boolean", nullable: false),
                    LastValidatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false),
                    UserCreatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserCreatedName = table.Column<string>(type: "text", nullable: true),
                    UserLastUpdatedId = table.Column<Guid>(type: "uuid", nullable: true),
                    UserLastUpdateName = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ExchangeConnections", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_TradingBots_ExchangeConnectionId",
                table: "TradingBots",
                column: "ExchangeConnectionId");

            migrationBuilder.CreateIndex(
                name: "IX_ExchangeConnections_UserId_Venue_IsActive",
                table: "ExchangeConnections",
                columns: new[] { "UserId", "Venue", "IsActive" });

            migrationBuilder.AddForeignKey(
                name: "FK_TradingBots_ExchangeConnections_ExchangeConnectionId",
                table: "TradingBots",
                column: "ExchangeConnectionId",
                principalTable: "ExchangeConnections",
                principalColumn: "Id",
                onDelete: ReferentialAction.SetNull);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_TradingBots_ExchangeConnections_ExchangeConnectionId",
                table: "TradingBots");

            migrationBuilder.DropTable(
                name: "ExchangeConnections");

            migrationBuilder.DropIndex(
                name: "IX_TradingBots_ExchangeConnectionId",
                table: "TradingBots");

            migrationBuilder.DropColumn(
                name: "ExchangeConnectionId",
                table: "TradingBots");
        }
    }
}
