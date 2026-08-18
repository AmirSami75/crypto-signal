# CryptoSignal.Auth

Authentication, users, roles and permissions. Depends on `CryptoSignal.Infra` and is consumed by
`CryptoSignal.Api`, which supplies the concrete `User` entity, the `DbContext` and the thin
controllers that inherit from the base controllers here.

Ported from an in-house library and retargeted to **net10.0** / **PostgreSQL**.

## What it provides

| Area | Contents |
| --- | --- |
| `Domain/Models` | `Role`, `Permission`, `RolePermission`, `UserRole`, `LoginHistory` |
| `Domain/Enums` | `PermissionType`, `LoginStatus`, `LoginType`, `UserType` |
| `Adapter/Presistence` | EF Core entity configurations and the `IEntitySeedData` seeders |
| `Adapter/Repos` | `IBaseUserRepo<T>`, `IRoleRepo`, `IPermissionRepo`, `ILoginHistoryRepo`, … |
| `API/Controllers/v1` | `BaseAuthController<...>`, `BaseUserController<...>`, role and permission controllers |
| `API/Attributes/Permissions` | `[CustomAuthorize]`, `[Permission(PermissionType.X)]`, `PermissionHandler` |
| `Application/Services` | `IAuthService<TUser>` — token issue, password hashing and verification |
| `Application/DTOs` | Login, session, user, role and permission contracts |
| `Application/Validators` | FluentValidation rules, including password strength |
| `Tooling/Registrations` | `InjectJwtAuth<TUser>()` |

`Docs/Permissions_Documents.pdf` describes the permission catalogue.

## Authorization model

Permissions are claims resolved through `UserRoles → Role → RolePermissions → Permission`. A login
eager-loads that whole graph, so `BaseAuthController.FetchUserEntity` overrides must include every
level of it.

> **`[Permission]` is inert on its own.** `PermissionHandler` only runs when the controller also
> carries `[CustomAuthorize]`. A controller with `[Permission]` and no `[CustomAuthorize]` is
> effectively unprotected. `[ControllerInfo(name, caption)]` is likewise mandatory — the permission
> seeder reads it to name the generated permissions.

## Bootstrap

`UserSeeder` creates the `cs-admin` superadmin on first start from
`API_Settings:Bootstrap:SuperAdminPassword`, flagged for a mandatory password change at first login.
Outside `Development` the seeder **throws** when that key is absent rather than fall back to a
password that lives in the source tree. The seeders run in order after `EnsureCreatedAsync`:
permissions (3) → roles (4) → users (5).

## Tokens

`AuthService.GenerateToken` signs with `HmacSha256`, hence the ≥ 32-byte `SecretKey` requirement
enforced in `InjectJwtAuth`. Tokens are signed but **not** encrypted — `EncryptingCredentials` is
left commented out, and no `TokenDecryptionKey` is configured to match.

## Build notes

`TreatWarningsAsErrors` is `false` for this project only, for the same reason as
`CryptoSignal.Infra`: keeping the ported sources close to upstream.
