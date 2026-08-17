# Live-trading safety policy

Status: Initial policy, mandatory for all implementation work  
Effective date: 2026-08-17  
Related tracker item: `PLAT-004`

## Purpose

This policy defines the minimum controls required before the platform may create an order
on an exchange. It applies to backend APIs, workers, Django Admin, the React dashboard,
scheduled strategies, manual operators, and every exchange adapter.

The platform is a research and operations system first. Real-money execution is disabled
by default and is not enabled merely because an exchange adapter or order endpoint exists.

## Core rule

**A model signal is evidence, not authorization.**

Every exchange order must originate from a durable order intent and pass an independent,
recorded risk decision. No UI, administrator, API endpoint, worker, model, script, or
exchange adapter may bypass that workflow.

When information is missing, stale, inconsistent, ambiguous, or unavailable, the system
must fail closed and send no new order.

## Supported operating modes

Every strategy, signal, credential, order intent, order, fill, balance, and position is
bound to exactly one operating mode:

- `PAPER`: local simulated execution and the default mode.
- `SANDBOX`: an exchange-provided test environment with no real funds.
- `LIVE`: real funds; unavailable until all documented promotion gates pass.

Records from different modes must not share a portfolio, order chain, performance series,
or reconciliation result. The current mode must be prominent in the dashboard and every
sensitive confirmation dialog.

## Fail-closed defaults

Until explicitly configured and approved, the effective defaults are:

| Control | Default |
|---|---|
| Live execution enabled | `false` |
| Allowed live symbols | empty set |
| Allowed product type | spot only |
| Leverage | `1` |
| Short selling | disabled |
| Maximum live order notional | `0` |
| Maximum live position notional | `0` |
| Maximum live daily loss | `0` |
| Maximum live drawdown | `0` |
| Maximum live order frequency | `0` |
| Human approval | required |
| Withdrawal permission | forbidden |

A zero or missing limit denies the action; it never means unlimited.

Before restricted live operation, an authorized risk administrator must set conservative,
nonzero limits. Initial live orders must use the exchange's minimum practical spot size or
a smaller predeclared cap, whichever results in less exposure. Limit changes require audit
records and must not take effect through an unreviewed code deployment.

## Exchange account and credential requirements

- Use a dedicated exchange subaccount when the exchange supports one.
- API keys must have only the permissions required for the current phase.
- Start with read-only production credentials.
- A live trading key may have trading permission but must not have withdrawals, transfers,
  key management, or unrelated account permissions.
- Apply exchange IP restrictions when supported.
- Store secrets in an approved encrypted store or secret manager, never source control,
  frontend code, database plaintext, job payloads, analytics events, or logs.
- The API may return a credential identifier and health state, but never secret material.
- Rotation, revocation, and last-verification timestamps must be recorded.
- A credential is bound to one exchange, account/subaccount, and operating mode.
- Any unexpected permission or account change disables execution and creates an incident.

## Instrument restrictions

Initial live support is limited to explicitly allowlisted spot pairs. The platform must
reject:

- margin, futures, perpetuals, options, lending, staking, and leveraged tokens;
- short positions or orders that would create a negative asset balance;
- symbols that are paused, delisted, in auction, or outside the configured allowlist;
- orders that violate exchange precision, step size, minimum size, or minimum notional;
- conversions or transfers that do not pass the same intent and risk workflow.

Adding leverage or derivatives requires a new ADR, risk model, test plan, and explicit
approval. It is not an extension of the initial spot implementation.

## Required pre-trade checks

The risk engine must evaluate all checks from one consistent snapshot and record their
inputs and outcomes. An order is denied if any required check cannot complete.

At minimum, validate:

1. Operating mode and strategy are enabled.
2. The deployed model version is approved and not retired.
3. The signal belongs to the intended model, instrument, interval, and completed candle.
4. The signal has not already produced an order intent.
5. Signal, candle, price, balance, position, fee, and instrument metadata are fresh.
6. The market is allowlisted and currently tradable.
7. Side, type, quantity, price, precision, and time-in-force are supported.
8. Estimated notional is above the exchange minimum and below the configured maximum.
9. Resulting position, concentration, gross exposure, and quote reserve remain within limits.
10. Daily realized/unrealized loss and drawdown remain within limits.
11. Order frequency, turnover, consecutive-loss, and duplicate-intent limits are satisfied.
12. There is sufficient available balance after existing reservations and open orders.
13. Exchange connectivity and reconciliation state are healthy.
14. The global, exchange, account, and strategy kill switches are clear.
15. Required human approval is valid, unexpired, and tied to the exact order preview.

Risk decisions are immutable. If an approved intent changes in symbol, side, size, price,
type, account, model, or mode, it requires a new risk decision and approval.

## Freshness and timing

- Signals may use completed candles only.
- A signal expires at the configured deadline and no later than the next strategy decision
  boundary unless a stricter limit is defined.
- Execution pricing must come from a current market snapshot with a recorded exchange time
  and receipt time.
- Balance, position, product rules, and fee schedules must be refreshed within their
  configured limits before submission.
- Clock drift beyond the configured tolerance disables authenticated exchange mutations.
- A reconnect does not make cached data fresh; required snapshots must be reacquired.

Freshness limits are explicit configuration values. Missing limits or timestamps cause a
rejection rather than falling back to an assumed value.

## Order intent, idempotency, and retries

- Every order begins as an immutable order intent with a stable internal identifier.
- Each exchange submission uses a stable unique client order identifier where supported.
- Database constraints prevent more than one intent for the same strategy decision.
- Repeated worker delivery returns the existing order/result instead of submitting again.
- Read-only requests may retry with bounded exponential backoff and jitter.
- Order submission, replacement, and cancellation are not blindly retried.
- When a mutation outcome is ambiguous, reconcile by client identifier and exchange state
  before deciding whether any further mutation is safe.
- An unresolved ambiguous result disables new strategy orders for the affected account and
  creates an incident.

## Manual approval

Restricted live operation requires explicit human approval for each order intent:

- The approver must have the dedicated live-order approval permission.
- The approver must not approve an expired intent.
- Approval displays mode, exchange, account, symbol, side, order type, size, estimated
  notional, price/slippage guard, fees, resulting exposure, model/signal, and risk checks.
- Approval is bound to the exact preview and expires after a short configured interval.
- Any material change invalidates the approval.
- The requestor and approver should be different users when more than one operator exists.
- Approval and rejection are audited with actor, timestamp, request ID, and reason.

Automatic execution is a later promotion decision. It cannot be enabled by setting the
manual-approval flag to false before the restricted-live evidence gate passes.

## Kill switches

The platform provides independent kill switches at these scopes:

- global platform;
- operating mode;
- exchange;
- account/subaccount;
- strategy;
- instrument.

Activating a kill switch immediately blocks new intents and submissions in its scope.
Cancellation of open orders is a separate explicit action because mass cancellation may
itself fail or increase risk. The dashboard must show switch state prominently, and all
changes must be audited.

Automatic kill-switch triggers include, at minimum:

- loss or drawdown limit reached;
- stale market or account data;
- reconciliation mismatch;
- repeated exchange authentication or permission failure;
- unknown or impossible order state;
- repeated worker/job failure;
- unexpected position, negative balance, or over-limit exposure;
- clock drift or prolonged market-stream outage;
- risk-engine or database unavailability.

## Order types and price protection

- Initial live operation supports only explicitly approved spot order types.
- Market orders require a maximum notional and a price/slippage protection policy.
- Limit orders require a price-distance guard and explicit time-in-force.
- Orders outside configured reference-price deviation are rejected.
- Partial fills, fees in alternate assets, and residual balances must be handled explicitly.
- An order preview is advisory; all checks are repeated immediately before submission.

## Reconciliation

Exchange state is authoritative for actual orders, fills, and balances. PostgreSQL is the
platform's durable operational record. The reconciliation worker must:

- query orders and fills after submissions and reconnects;
- consume authenticated user-order events when available;
- tolerate duplicate, delayed, missing, and reordered events;
- compare balances, reservations, open orders, fills, and positions;
- record the source and time of every update;
- create an incident for unexplained differences;
- prevent new strategy orders while a material mismatch remains unresolved.

WebSocket events improve latency but are never the only reconciliation source.

## Portfolio and loss controls

All calculations use decimal arithmetic and conservative valuation. Required limits include:

- maximum order notional;
- maximum position per asset and pair;
- maximum gross and net exposure;
- minimum quote-currency reserve;
- maximum daily realized plus unrealized loss;
- maximum peak-to-trough drawdown;
- maximum order count and turnover per period;
- maximum consecutive rejected or failed orders.

Fees, estimated slippage, open-order reservations, and pending intents count toward limits.
If valuation data is stale or a currency cannot be converted conservatively, deny the order.

## Audit and observability

The platform records a causal chain from candle to final account state:

```text
candle -> model version -> signal -> strategy decision -> order intent
       -> risk decision -> approval -> exchange request/response
       -> order events -> fills -> balance/position -> reconciliation
```

Logs and audit events must include correlation identifiers but no credentials or sensitive
headers. Monitoring covers data freshness, jobs, model state, exchange connectivity, risk
rejections, order latency/state, reconciliation drift, exposure, losses, and kill switches.

Critical alerts must be tested through an end-to-end delivery path. Configuring an alert
without verifying receipt does not satisfy a safety gate.

## Operational requirements

Before live mode, the team must have tested runbooks for:

- global stop and strategy disablement;
- credential revocation and rotation;
- exchange outage or maintenance;
- unknown, stuck, partially filled, or duplicated orders;
- reconciliation mismatch;
- worker or database failure;
- application rollback;
- database backup and restore;
- lost operator access.

Deployments that change execution, risk, adapter, credential, or accounting code require
paper/sandbox regression tests before promotion. Production migrations must have rollback
or forward-recovery procedures.

## Promotion gates

Live operation is prohibited until evidence exists for each preceding gate:

1. **Platform:** authentication, least privilege, audit trail, durable jobs, backups.
2. **Paper:** deterministic broker, accounting invariants, idempotency, reconciliation soak.
3. **Adapter:** contract tests, precision/limit tests, ambiguous-write recovery.
4. **Risk:** non-bypassable limits, freshness rejection, approvals, kill switches.
5. **Sandbox:** continuous operation, tested alerts/runbooks, no unexplained drift.
6. **Read-only production:** balances, products, fees, and history reconcile.
7. **Restricted live:** minimum-size, spot-only, manually approved orders.
8. **Automation:** separate approval using restricted-live evidence and tighter limits.

Failure at any gate returns the system to the preceding safe mode. Time spent running is
not evidence if failures, missed signals, or reconciliation gaps are hidden.

## Prohibited actions

The following are prohibited in the initial platform:

- withdrawal-enabled API credentials;
- direct model-to-exchange calls;
- direct frontend-to-exchange calls;
- order placement inside a normal HTTP request;
- unbounded order, position, loss, drawdown, or retry settings;
- using floating-point values for monetary state;
- silently treating missing data or errors as permission to trade;
- mixing paper, sandbox, and live portfolios or metrics;
- changing an order after approval without a new decision;
- enabling live automation solely because a historical backtest is positive.

## Review

Review this policy before each promotion gate and whenever the platform adds a new exchange,
order type, asset class, leverage, custody model, credential scheme, or automatic execution
path. Material changes require a new recorded decision and regression evidence.
