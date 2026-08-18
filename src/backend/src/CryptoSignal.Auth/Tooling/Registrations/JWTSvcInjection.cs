using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using CryptoSignal.Auth.Adapter.Repos.Contracts;
using CryptoSignal.Auth.Domain.Models;
using CryptoSignal.Infra.Base.Auth;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Extensions.Auth;
using CryptoSignal.Infra.Settings;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Claims;
using System.Text;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using CryptoSignal.Infra.Base.Enums;

namespace CryptoSignal.Auth.Tooling.Registrations;

public static class JWTSvcInjection
{
    public static void InjectJwtAuth<TEntity>(this IServiceCollection services)
        where TEntity : BaseUser
    {
        // You must have already bound JwtSettings somewhere:
        // services.Configure<JwtSettings>(configuration.GetSection("API_Settings:Jwt"));
        // or similar.

        // NOTE: Building a ServiceProvider inside Configure is not ideal,
        // but keeps this extension simple and self-contained.
        var sp = services.BuildServiceProvider();
        var jwtSettings = sp.GetRequiredService<IOptions<JwtSettings>>().Value;

        // Validate here rather than letting the token handler fail later: HmacSha256 rejects keys
        // shorter than 256 bits, and it does so with an IDX10653 that names no configuration key.
        if (string.IsNullOrWhiteSpace(jwtSettings.SecretKey))
            throw new InvalidOperationException(
                "API_Settings:Jwt:SecretKey is required. Supply it out of band — for example the " +
                "API_Settings__Jwt__SecretKey environment variable.");

        if (Encoding.UTF8.GetByteCount(jwtSettings.SecretKey) < 32)
            throw new InvalidOperationException(
                "API_Settings:Jwt:SecretKey must be at least 32 bytes (256 bits) because tokens are " +
                "signed with HMAC-SHA256.");

        var secretKey = Encoding.UTF8.GetBytes(jwtSettings.SecretKey);

        var validationParameters = new TokenValidationParameters
        {
            ClockSkew = TimeSpan.Zero, // no extra time window
            RequireSignedTokens = true,
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(secretKey),

            RequireExpirationTime = true,
            ValidateLifetime = true,

            ValidateAudience = true,
            ValidAudience = jwtSettings.Audience,

            ValidateIssuer = true,
            ValidIssuer = jwtSettings.Issuer,

            // Tokens are currently signed but not encrypted (GenerateToken sets no
            // EncryptingCredentials), so no TokenDecryptionKey is configured. If encryption is
            // enabled later, derive the key from JwtSettings.EncryptKey and set it here.
            // TokenDecryptionKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSettings.EncryptKey))
        };

        services
            .AddAuthentication(options =>
            {
                options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
                options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
                options.DefaultScheme = JwtBearerDefaults.AuthenticationScheme;
            })
            .AddJwtBearer(options =>
            {
                // In dev / Docker you’re on HTTP; for real prod behind TLS, set to true.
                options.RequireHttpsMetadata = false;
                options.SaveToken = true;
                options.TokenValidationParameters = validationParameters;

                options.Events = new JwtBearerEvents
                {
                    OnMessageReceived = context =>
                    {
                        var authHeaders = context.Request.Headers.Authorization;
                        var cookieToken = context.Request.Cookies["Authorization"];

                        // 🔍 Debug logging
                        // Console.WriteLine("========== JWT OnMessageReceived ==========");
                        // Console.WriteLine("[JWT DEBUG] Path: " + context.Request.Path);
                        // Console.WriteLine("[JWT DEBUG] Raw Authorization headers: '" +
                        //                   string.Join(" | ", authHeaders.ToArray()) + "'");
                        // Console.WriteLine("[JWT DEBUG] Cookie Authorization: '" + cookieToken + "'");

                        string? bearerToken = null;

                        // 1) Normalize all header values:
                        //    Split on ',' in case they were merged: "Bearer x, Bearer y"
                        var candidates = authHeaders
                            .SelectMany(h => h.Split(',', StringSplitOptions.RemoveEmptyEntries))
                            .Select(h => h.Trim());

                        // 2) Take the first proper "Bearer <token>" entry
                        foreach (var candidate in candidates)
                        {
                            if (candidate.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
                            {
                                bearerToken = candidate["Bearer ".Length..].Trim();
                                break;
                            }
                        }

                        // 3) Fallback to cookie
                        if (string.IsNullOrEmpty(bearerToken) && !string.IsNullOrEmpty(cookieToken))
                        {
                            bearerToken = cookieToken;
                        }

                        context.Token = bearerToken;

                        // Console.WriteLine("[JWT DEBUG] Final context.Token: '" + context.Token + "'");
                        // Console.WriteLine("======================================");

                        return Task.CompletedTask;
                    },

                    OnTokenValidated = async context =>
                    {
                        try
                        {
                            var claimsIdentity = context.Principal?.Identity as ClaimsIdentity;

                            if (claimsIdentity?.Claims?.Any() != true)
                            {
                                // Console.WriteLine("[JWT DEBUG] OnTokenValidated: no claims present");
                                context.Fail("NoClaims");
                                context.Response.Headers["X-Auth-Error"] = "NoClaims";
                                return;
                            }

                            var securityStamp = claimsIdentity.FindFirstValue(CryptoSignalClaimTypes.SecurityStamp);
                            if (string.IsNullOrEmpty(securityStamp))
                            {
                                // Console.WriteLine("[JWT DEBUG] OnTokenValidated: missing security stamp");
                                context.Fail("MissingSecurityStamp");
                                context.Response.Headers["X-Auth-Error"] = "MissingSecurityStamp";
                                return;
                            }

                            var userId = context.Principal?.Identity?.GetUserId<Guid>() ?? Guid.Empty;
                            if (userId == Guid.Empty)
                            {
                                // Console.WriteLine("[JWT DEBUG] OnTokenValidated: invalid or missing userId claim");
                                context.Fail("InvalidUserId");
                                context.Response.Headers["X-Auth-Error"] = "InvalidUserId";
                                return;
                            }

                            var userRepo = context.HttpContext.RequestServices
                                .GetRequiredService<IBaseUserRepo<TEntity>>();

                            var user = await userRepo.TableNoTracking.FirstOrDefaultAsync(
                                p => p.Id == userId && !p.IsDeleted,
                                context.HttpContext.RequestAborted);

                            if (user is null)
                            {
                                // Console.WriteLine("[JWT DEBUG] OnTokenValidated: user not found in DB");
                                context.Fail("UserNotFound");
                                context.Response.Headers["X-Auth-Error"] = "UserNotFound";
                                return;
                            }

                            if (!string.Equals(user.SecurityStamp.ToString(), securityStamp,
                                    StringComparison.OrdinalIgnoreCase))
                            {
                                // Console.WriteLine(
                                //     "[JWT DEBUG] OnTokenValidated: security stamp mismatch. DB='{0}', token='{1}'",
                                //     user.SecurityStamp, securityStamp);
                                context.Fail("SecurityStampMismatch");
                                context.Response.Headers["X-Auth-Error"] = "SecurityStampMismatch";
                                return;
                            }

                            // Console.WriteLine("[JWT DEBUG] OnTokenValidated: SUCCESS for user " + user.Id);
                            context.Success();
                        }
                        catch (Exception exp)
                        {
                            // Console.WriteLine("[JWT DEBUG] OnTokenValidated: exception: " + exp);
                            context.Fail("Exception");
                            context.Response.Headers["X-Auth-Error"] = "Exception";
                        }
                    },

                    OnAuthenticationFailed = context =>
                    {
                        // Any failure in token validation (signature, expired, malformed, etc.)
                        context.Response.Headers["X-Auth-Error"] = "AuthenticationFailed";
                        Console.WriteLine("[JWT DEBUG] Auth failed: " + context.Exception);
                        return Task.CompletedTask;
                    },

                    OnChallenge = context =>
                    {
                        // We are taking over the 401 response
                        context.HandleResponse();

                        var errorCode = context.Response.Headers.TryGetValue("X-Auth-Error", out var v)
                            ? v.ToString()
                            : context.AuthenticateFailure?.Message ?? "خطای احراز هویت";

                        context.Response.StatusCode = (int)ApiResultStatusCode.Unauthorized;
                        context.Response.ContentType = "application/json; charset=utf-8";

                        var payload = System.Text.Json.JsonSerializer.Serialize(new
                        {
                            error = "unauthorized",
                            code = errorCode
                        });

                        return context.Response.WriteAsync(payload);
                    }
                };
            });
    }
}