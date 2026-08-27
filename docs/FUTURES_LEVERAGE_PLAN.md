# Futures + Leverage + Bybit Demo — Design

*2026-08-27 · follows docs/ROADMAP.md Track 2 (futures) + the user's option B (Bybit demo)*

## Why Bybit demo

Bybit's **demo trading** (`https://api-demo.bybit.com`, v5 unified API) is a full futures
order-lifecycle environment with pre-funded virtual USDT: place/cancel/position/closed-PnL,
set-leverage, demo-apply-money — the real thing without real funds. It is the venue the user
chose for futures work, and it is where leverage can be exercised honestly.

## Leverage semantics — the one decision that matters

`QuoteNotionalPerTrade` keeps its meaning: **position notional (exposure, in quote)**. Nothing
existing changes for spot, because spot has `Leverage = 1` and margin equals exposure there.

New field `Leverage` (int, default 1). On a leveraged venue:

- position notional = `QuoteNotionalPerTrade` (unchanged)
- margin committed = `QuoteNotionalPerTrade / Leverage`
- `MaxPositionNotional` still caps exposure (the position notional)
- the **balance check compares margin against available collateral**, not exposure — on spot
  (leverage 1) this collapses to today's behaviour, so no existing bot changes

Rules that keep it fail-closed:

- spot venues (`Replay`, `BinanceTestnet`, `BinanceMainnet`) force `Leverage = 1`; any other
  value is rejected at bot create/update
- futures venues cap leverage at `Trading:Risk:MaxLeverage` (config); an unset cap = 0 = denied
- `allowShort` is already the policy gate for shorts; futures permits shorts only when
  `Trading:Risk:AllowShorting` is true (unchanged)

## Touch points

| Layer | Change |
|---|---|
| `MarketVenue` | add `Bybit = 5` |
| `TradingBot` | add `Leverage` (int, default 1) + EF migration |
| `ExchangeOptions` / `BinanceEndpoints` | add `Bybit` venue → `https://api-demo.bybit.com` |
| `TradingHttpClients` / `Program.cs` | add `Bybit` named client + `AddVenueClient` |
| `TradingRiskOptions` | add `MaxLeverage` (int, default 0 = unset = deny) |
| `BrokerOrderRequest` | add `Leverage` (int, default 1) |
| `OrderIntent` | add `Leverage` |
| `RiskEngine` / `RiskSnapshot` | `EstimatedMargin = EstimatedNotional / Leverage`; balance check uses margin; leverage-cap check |
| `BotController` + DTOs | accept/validate `Leverage`, surface it |
| `BybitKlineSource` | market data (interval tokens `5m→"5"`, `1h→"60"`…) |
| `BybitFuturesBroker` | HMAC-SHA256 v5 signing; set-leverage before open; place/cancel/position |

## Bybit v5 specifics (from probing)

- Kline: `GET /v5/market/kline?category=linear&symbol=BTCUSDT&interval=5&limit=N` — list is
  **newest-first**, 7-tuple `[start, open, high, low, close, volume, turnover]`, no auth.
- Signing: HMAC-SHA256 over `timestamp + api_key + recv_window + query(optional) + body(optional)`,
  headers `X-BAPI-API-KEY/TIMESTAMP/RECV-WINDOW/SIGN`. Query must be the **raw** URL-encoded
  string actually sent; body the **raw** JSON bytes.
- Order: `POST /v5/order/create` (Market, `category=linear`, `positionIdx=0`, `timeInForce=GTC`).
- Leverage: `POST /v5/position/set-leverage` (`category=linear`, `symbol`, `buyLeverage`,
  `sellLeverage`) — must run before the first open on a symbol.
- Balance: `GET /v5/account/wallet-balance?accountType=UNIFIED` → `totalAvailableBalance`.

## Safety posture (unchanged, restated)

No LIVE broker is registered; Bybit is **Sandbox only** and points at the demo host, so a
Sandbox bot on Bybit cannot touch real funds — unlike the Bitunix trap (Sandbox → production).
That Bitunix hazard is fixed in this same change: Bitunix will stop claiming Sandbox.

## Out of scope now

Isolated margin, liquidation modelling in the risk engine, funding-rate awareness, partial-close
brackets, and anything real-money. Demo first; the promotion gate and paper soak decide what
graduates.
