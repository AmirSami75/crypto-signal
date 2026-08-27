/**
 * Types mirroring the API's wire contract.
 *
 * These describe what the API *sends*, not what the app would prefer to receive. The reshaping into
 * something uniform happens in `api.ts`; keeping the raw shapes named and separate is what makes
 * that normalisation reviewable — each awkward variant below corresponds to one branch there.
 */

/** `ApiResultStatusCode` on the server. Numeric, because it doubles as the HTTP status. */
export type ApiStatusCode = 200 | 204 | 400 | 401 | 403 | 404 | 409 | 422 | 429 | 500 | 503

/**
 * The same enum as the server sometimes spells it: as a member *name*, because MVC serialises with
 * `StringEnumConverter` while the exception middleware and the rate limiter emit the number.
 */
export type ApiStatusName =
  | 'Success'
  | 'NoContent'
  | 'BadRequest'
  | 'Unauthorized'
  | 'Forbidden'
  | 'NotFound'
  | 'Conflict'
  | 'ValidationError'
  | 'ServerError'
  | 'ServiceUnavailable'

/**
 * Every envelope the API is known to produce, as a union. Six shapes were confirmed against the
 * running service; see `normalise()` in `api.ts` for where each one comes from and what it means.
 */
export type RawEnvelope =
  /** MVC, success or a filter-level validation failure: camelCase keys, enum as a name. */
  | {
      data?: unknown
      isSuccess?: boolean
      statusCode?: ApiStatusName | ApiStatusCode
      message?: string | null
    }
  /** `UnifiedExceptionHandlerMiddleware`: PascalCase keys, enum as a number. */
  | {
      IsSuccess?: boolean
      StatusCode?: ApiStatusCode
      Message?: string | null
    }
  /** The JWT bearer `OnChallenge` handler: no envelope at all. */
  | { error?: string; code?: string }

/**
 * The shape the middleware puts inside `Message` when the environment is Development: the real text
 * is nested under `Exception`, with a full server stack trace alongside it.
 */
export type DevErrorPayload = {
  Exception?: string
  StackTrace?: string
}

/**
 * Paged listing envelope.
 *
 * Both counts are sent and they mean different things: `totalRecords` is the size of the whole
 * filtered set and is what the pager divides, while `count` is how many rows this particular page
 * carries. Reading `count` as the total shows "1 record" on a 62-row table, which is why they are
 * named apart here rather than collapsed into one field.
 */
export type PagedResult<T> = {
  totalRecords: number
  items: T[]
  pageNumber: number
  pageSize: number
  count: number
}

/**
 * Audit trail on every `BaseOutputDto`, and an unusual shape worth naming.
 *
 * `creationDate` is *not* a date: it is the Jalali date and the acting user joined by a space —
 * `"1405/06/01 System Administrator"` — because the server interpolates both into one string. The
 * date is the first whitespace-delimited token; the remainder is a display name that may itself
 * contain spaces. `jalaliDate()` and `auditActor()` in `lib/format.ts` do that split in one place.
 *
 * When a row has never been updated the modification pair is the literal `" "`: the interpolation
 * runs over two nulls and yields a lone separator, not null. Anything rendering these has to treat
 * whitespace-only as absent — a bare `?? '—'` will happily print a blank cell.
 */
export type AuditFields = {
  creationDate: string
  creationTime: string
  modificationDate: string | null
  modificationTime: string | null
  userCreatedName: string | null
  userLastUpdateName: string | null
}

/** A permission as the catalogue returns it — `name` is the string `can()` matches against. */
export type Permission = {
  id: string
  name: string
  title: string
} & AuditFields

/** `RoleType`, already resolved to its Persian display text by the server rather than sent as a name. */
export type RoleTypeLabel = 'مدیر سیستم' | 'کاربر عادی' | 'کاربر'

/**
 * A role. `permissions` is the full nested catalogue subset on every *role* endpoint (list, paged,
 * by-id) — but see `Role` inside `User`, where the projection leaves it null.
 */
export type Role = {
  id: string
  name: string
  title: string
  type: RoleTypeLabel | string | null
  permissions: Permission[] | null
} & AuditFields

/**
 * A role as it appears *nested inside a user*, which is a strictly smaller shape.
 *
 * `UserOutputDto` projects only three columns out of the join, so `type` and `permissions` come back
 * null and the audit strings come back `" "` — the row was never actually mapped through
 * `RoleOutputDto`'s enrichment pass. Reading `user.roles[0].permissions.length` therefore throws.
 * Fetch the role by id when its permissions are needed.
 */
export type RoleRef = Pick<Role, 'id' | 'name' | 'title'>

/** Create/update payload for a role. `permissions` carries ids only; the server rejects an empty list. */
export type RoleInput = {
  id?: string
  name: string
  title: string
  permissions: Array<{ id: string }>
}

/** `UserType`, sent and accepted as the enum *name* — the `[Display]` text happens to be Latin too. */
export type UserTypeName = 'Administrator' | 'Trader' | 'Analyst' | 'Viewer'

export type User = {
  id: string
  fullName: string
  userName: string
  email: string | null
  phone: string | null
  mobile: string | null
  address: string | null
  personelCode: string | null
  isActive: boolean
  isLocked: boolean
  parentId: string | null
  /** Resolved server-side, so the table can name the parent without a second fetch. */
  parentName: string | null
  userType: UserTypeName | null
  /** Partial: ids and names only. See `RoleRef`. */
  roles: RoleRef[] | null
} & AuditFields

/**
 * Create/update payload for a user.
 *
 * There is no password field on purpose — the server hashes `AuthGlobalVariables.DefaultPassword`
 * for a new account and flags it for a forced change, so the operator never chooses one. `roles`
 * must be non-empty or `BaseUserInputDto.Validate` rejects the whole payload.
 */
export type UserInput = {
  id?: string
  fullName: string
  userName: string
  email?: string | null
  phone?: string | null
  mobile?: string | null
  address?: string | null
  personelCode?: string | null
  parentId?: string | null
  userType?: UserTypeName | null
  roles: Array<{ id: string }>
}

/**
 * One sign-in attempt. `status` is the `LoginStatus` enum name, and `dateTime` is a full Jalali
 * timestamp (`"1405/06/01 11:41:43"`) — unlike `creationDate`, no actor name is appended to it.
 *
 * The endpoint returns *every* user's attempts, not the caller's; the screen labels it accordingly.
 */
export type LoginHistoryEntry = {
  id: string
  ip: string | null
  userAgent: string | null
  dateTime: string
  status: 'Success' | 'Error' | string
} & AuditFields

/**
 * Query filters for the paged user listing.
 *
 * Keys are PascalCase to match the OpenAPI spec exactly. ASP.NET binds query strings
 * case-insensitively so camelCase would also work today, but matching the published contract keeps
 * the client honest if that ever tightens.
 */
export type UserFilters = {
  UserName?: string
  FullName?: string
  PersonelCode?: string
  Mobile?: string
  UserType?: UserTypeName | ''
  /** Tri-state: `undefined` means "either", not "false". */
  IsActive?: boolean
  IsLocked?: boolean
}

/** Both the role and the permission listings filter on the same single field. */
export type TitleFilter = { Title?: string }

export type LoginHistoryFilters = { IP?: string }

/** Path segments shared by every paged endpoint: `/{page}/{pageSize}/{desc}`. */
export type PageQuery = {
  page: number
  pageSize: number
  /** Newest-first when true. Applies to the entity's creation order. */
  desc?: boolean
}

/**
 * The authenticated session, as `POST /api/v1/auth/login` returns it in `data`.
 *
 * `permissions` is empty for a superadmin: the server skips permission collection entirely when the
 * user holds a superadmin role, so an empty array means "everything" there and "nothing" otherwise.
 * Never read it without checking `isSuperAdmin` first — `can()` in `auth/permissions.ts` exists so
 * that check happens in exactly one place.
 */
export type SessionUser = {
  userId: string
  userName: string
  fullName: string
  token: string
  /** ISO-8601 UTC instant. Compared against the clock on load to drop a stale session. */
  tokenExpiry: string
  isSuperAdmin: boolean
  isParent: boolean
  requiresPasswordChange: boolean
  roles: string[]
  permissions: string[]
  userType: string | null
}

export type LoginRequest = {
  userName: string
  password: string
}

export type RegisterRequest = {
  fullName: string
  userName: string
  password: string
  confirmPassword: string
  email?: string
  mobile?: string
}

export type ChangePasswordRequest = {
  currentPass: string
  newPass: string
  confirmNewPass: string
}

/** `GET /api/v1/platform`. Top-level, not wrapped in an `ApiResult`. */
export type PlatformInfo = {
  operatingMode: string
  executionPolicy: string
}

/**
 * `GET /health/ready`. Top-level, not wrapped in an `ApiResult`.
 *
 * Serialised by `Results.Json`, so camelCase from System.Text.Json's web defaults — not by the
 * Newtonsoft pipeline the MVC controllers use. Answers 200 when `status` is `"healthy"` and **503**
 * when it is `"degraded"`; both bodies are shaped the same, which is why the client reads the 503 one
 * instead of discarding it.
 */
export type Readiness = {
  service: string
  status: string
  timestamp: string
  /** Absent rather than empty when the report carries no dependency detail. */
  dependencies?: Array<{ name: string; status: string; detail?: string | null }> | null
}

// ─── Trading ──────────────────────────────────────────────────────────────────────────────────────
//
// Every enum below arrives as a *string*, not a number. The MVC pipeline is Newtonsoft with
// `StringEnumConverter`, so `OperatingMode.Paper` serialises as `"Paper"` — which is why these are
// string unions rather than numeric ones, and why a widened server enum shows up as a type error here
// instead of as a mystery integer on screen.
//
// Money is a `decimal` on the server and arrives as a JSON number. That is a lossy channel in
// principle, and it is tolerable in exactly one direction: these values are *displayed*, never summed
// into a stored total and never compared for equality. Anything that must be exact stays server-side.

export type OperatingModeName = 'Paper' | 'Sandbox' | 'Live'
export type MarketVenueName = 'Replay' | 'BinanceTestnet' | 'BinanceMainnet' | 'Bitunix' | 'Bybit'
export type BotStatusName = 'Draft' | 'Active' | 'Paused' | 'Stopped' | 'Faulted'
export type TradeDirectionName = 'Long' | 'Short' | 'Flat'
export type BotDecisionActionName = 'Hold' | 'Open' | 'Close' | 'AdjustBracket'
export type PositionStatusName = 'Open' | 'Closed'
export type KillSwitchScopeName = 'Global' | 'OperatingMode' | 'Exchange' | 'Bot' | 'Symbol'
export type OrderSideName = 'Buy' | 'Sell'
export type OrderTypeName = 'Market' | 'Limit' | 'StopLoss' | 'StopLossLimit' | 'TakeProfit' | 'TakeProfitLimit'
export type TimeInForceName = 'GoodTillCancel' | 'ImmediateOrCancel' | 'FillOrKill'

export type PositionCloseReasonName =
  | 'TakeProfitTouched'
  | 'StopLossTouched'
  | 'MaxHoldingPeriodsReached'
  | 'DirectionReversed'
  | 'ManualClose'
  | 'KillSwitch'
  | 'BotStopped'
  | 'Liquidation'

export type OrderIntentStatusName =
  | 'Draft'
  | 'RiskApproved'
  | 'RiskDenied'
  | 'Submitting'
  | 'Submitted'
  | 'PartiallyFilled'
  | 'Filled'
  | 'Cancelled'
  | 'Rejected'
  | 'Expired'
  | 'Ambiguous'

export type ExchangeOrderStatusName =
  | 'New'
  | 'PartiallyFilled'
  | 'Filled'
  | 'Cancelled'
  | 'Rejected'
  | 'Expired'
  | 'PendingCancel'
  | 'Unknown'

export type BotAuditEventTypeName =
  | 'CandleWindowRecorded'
  | 'ModelConsulted'
  | 'DecisionRecorded'
  | 'IntentCreated'
  | 'RiskEvaluated'
  | 'OrderSubmitted'
  | 'OrderAcknowledged'
  | 'OrderRejected'
  | 'FillRecorded'
  | 'PositionOpened'
  | 'PositionUpdated'
  | 'PositionClosed'
  | 'KillSwitchEngaged'
  | 'BotFaulted'
  | 'ConfigurationChanged'

// ─── Signals (capability 2) ───────────────────────────────────────────────────────────────────────

/**
 * `POST /api/v1/ml/signals`.
 *
 * The candle window is deliberately absent: the server fetches it from the configured venue, so the
 * browser cannot influence what the model was shown. `venue` is an override for the same reason it is
 * optional — the default is configured server-side, and a caller naming a different one is asking a
 * question about that venue, not switching the platform's source.
 */
export type SignalRequest = {
  symbol: string
  interval: string
  takeProfitPercent: number
  stopLossPercent: number
  allowShort: boolean
  /** 0 means "use the model's configured default", which is the normal case. */
  maxHoldingPeriods?: number
  /** 0 means "use the engine default". A floor above the model's ceiling filters out everything. */
  minimumConfidence?: number
  venue?: MarketVenueName
}

export type SignalLevels = {
  entryPrice: number
  takeProfitPrice: number
  stopLossPrice: number
  atr: number
  riskRewardRatio: number
  takeProfitAtr: number
  stopLossAtr: number
}

/** Probability each barrier is reached *first*, for the reported direction. Sums to 1. */
export type SignalProbabilities = {
  takeProfitFirst: number
  stopLossFirst: number
  timeout: number
}

/**
 * `levels` is null when the direction is `Flat` — there is no bracket for a bet nobody is placing.
 *
 * `barrierExtrapolated` matters more than it looks: it means the requested distance fell outside the
 * ATR span the model was fitted across, so `expectedValue` is an extension of the fitted surface
 * rather than a measurement on it. It gets its own warning in the UI, separate from `warning`, because
 * a percent-denominated request becomes a wide ATR bracket whenever the market is quiet.
 */
export type Signal = {
  symbol: string
  interval: string
  venue: MarketVenueName
  candleCount: number
  takeProfitPercent: number
  stopLossPercent: number
  allowShort: boolean
  direction: TradeDirectionName
  levels: SignalLevels | null
  confidence: number
  longConfidence: number
  shortConfidence: number
  probabilities: SignalProbabilities
  expectedValue: number
  candleOpenTime: string | null
  validUntil: string | null
  modelId: string
  modelVersion: string
  modelTrainedAt: string | null
  usedWildcardModel: boolean
  inputDigestSha256: string
  rationale: string[]
  warning: string
  barrierExtrapolated: boolean
  processingMilliseconds: number
}

// ─── Bots (capability 1) ──────────────────────────────────────────────────────────────────────────

/**
 * The bot form's payload.
 *
 * Every risk limit here **denies at zero** — none of them means "unlimited". The form says so next to
 * each field, because the natural reading of a blank number box is the opposite of what the server
 * does with it.
 *
 * `symbol`, `interval` and `operatingMode` are create-only. The server refuses to change them on an
 * existing bot: editing them in place would leave a paper bot's fills attached to a sandbox bot.
 */
/**
 * The self-learning loop's read side: closed positions joined to the decisions that opened them,
 * aggregated. A calibrated model shows bucket win rates rising in step with their centers; flat or
 * inverted rows are the earliest visible sign of drift.
 */
export type ConfidenceBucket = {
  lower: number
  upper: number
  trades: number
  wins: number
  totalPnl: number
}

export type SymbolOutcome = {
  symbol: string
  trades: number
  wins: number
  totalPnl: number
}

export type OutcomeReport = {
  sampleSize: number
  wins: number
  losses: number
  totalRealizedPnl: number
  averageRealizedPnl: number
  calibrationBuckets: ConfidenceBucket[]
  perSymbol: SymbolOutcome[]
}

/** One stored exchange connection as the API returns it. No secret material, ever. */
export type ExchangeConnection = {
  id: string
  venue: MarketVenueName
  label: string
  keyPreview: string
  isActive: boolean
  lastValidatedAt: string | null
  createdAt: string
}

export type ExchangeConnectionInput = {
  venue: MarketVenueName
  label: string
  apiKey: string
  apiSecret: string
}

export type BotInput = {
  name: string
  description?: string | null
  symbol: string
  interval: string
  venue: MarketVenueName
  operatingMode: OperatingModeName
  takeProfitPercent: number
  stopLossPercent: number
  allowShort: boolean
  leverage: number
  quoteNotionalPerTrade: number
  minimumConfidence: number
  maxHoldingPeriods: number
  cadenceSeconds: number
  maxOrderNotional: number
  maxPositionNotional: number
  maxDailyLoss: number
  maxDrawdown: number
  maxConcurrentPositions: number
  maxOrdersPerDay: number
  maxConsecutiveFailures: number
  maxSlippageBps: number
  expectedModelVersion?: string | null
  exchangeConnectionId?: string | null
}

export type BotSummary = {
  id: string
  name: string
  symbol: string
  interval: string
  venue: MarketVenueName
  operatingMode: OperatingModeName
  status: BotStatusName
  statusReason: string | null
  takeProfitPercent: number
  stopLossPercent: number
  allowShort: boolean
  leverage: number
  quoteNotionalPerTrade: number
  cadenceSeconds: number
  lastTickAt: string | null
  lastEvaluatedCandleOpenTime: string | null
  faultedAt: string | null
  createdAt: string
  openPositionCount: number
  realizedPnl: number
  /** Engaged switch covering this bot. It still shows as Active — the switch blocks new intents. */
  isBlockedByKillSwitch: boolean
}

export type BotRun = {
  id: string
  leaseOwner: string
  startedAt: string
  lastHeartbeatAt: string
  endedAt: string | null
  tickCount: number
  decisionCount: number
  orderCount: number
  errorCount: number
  consecutiveFailureCount: number
  lastError: string | null
  lastErrorAt: string | null
  lastTickAt: string | null
}

export type BotPosition = {
  id: string
  operatingMode: OperatingModeName
  venue: MarketVenueName
  symbol: string
  direction: TradeDirectionName
  status: PositionStatusName
  averageEntryPrice: number
  quantity: number
  entryNotional: number
  takeProfitPrice: number | null
  stopLossPrice: number | null
  openedAt: string
  closedAt: string | null
  barsHeld: number
  averageExitPrice: number | null
  closeReason: PositionCloseReasonName | null
  realizedPnl: number
  feesPaid: number
  unrealizedPnl: number | null
  lastMarkPrice: number | null
  lastMarkedAt: string | null
  maxAdverseExcursion: number
}

export type BotDetail = {
  id: string
  name: string
  description: string | null
  symbol: string
  interval: string
  venue: MarketVenueName
  operatingMode: OperatingModeName
  takeProfitPercent: number
  stopLossPercent: number
  allowShort: boolean
  leverage: number
  quoteNotionalPerTrade: number
  minimumConfidence: number
  maxHoldingPeriods: number
  cadenceSeconds: number
  status: BotStatusName
  statusReason: string | null
  faultedAt: string | null
  lastEvaluatedCandleOpenTime: string | null
  lastTickAt: string | null
  maxOrderNotional: number
  maxPositionNotional: number
  maxDailyLoss: number
  maxDrawdown: number
  maxConcurrentPositions: number
  maxOrdersPerDay: number
  maxConsecutiveFailures: number
  maxSlippageBps: number
  expectedModelVersion: string | null
  exchangeConnectionId: string | null
  createdAt: string
  updatedAt: string | null
  currentRun: BotRun | null
  openPositions: BotPosition[]
  realizedPnl: number
  closedPositionCount: number
  isBlockedByKillSwitch: boolean
}

/** Start, pause and stop all take a reason. It lands in the audit trail as the actor's own words. */
export type BotStatusChange = { reason: string }

// ─── The causal chain ─────────────────────────────────────────────────────────────────────────────

export type BotDecision = {
  id: string
  botId: string
  operatingMode: OperatingModeName
  symbol: string
  interval: string
  candleOpenTime: string
  candleWindowDigest: string
  action: BotDecisionActionName
  direction: TradeDirectionName
  reasonCode: string
  confidence: number
  longConfidence: number
  shortConfidence: number
  expectedValue: number
  probabilityTakeProfitFirst: number
  probabilityStopLossFirst: number
  probabilityTimeout: number
  entryPrice: number | null
  takeProfitPrice: number | null
  stopLossPrice: number | null
  atr: number | null
  riskRewardRatio: number | null
  modelId: string
  modelVersion: string
  modelTrainedAt: string | null
  usedWildcardModel: boolean
  barrierExtrapolated: boolean
  warning: string | null
  validUntil: string | null
  processingMilliseconds: number
  createdAt: string
}

/**
 * The risk engine's verdict, kept whether it allowed or denied.
 *
 * `failedChecks` is the server's CSV already split. A denial is evidence, not an error to hide, which
 * is why the orders view renders these rows rather than filtering them out.
 */
export type RiskDecision = {
  id: string
  allowed: boolean
  failedChecks: string[]
  detail: string | null
  snapshotJson: string | null
  evaluatedAt: string
}

export type OrderFill = {
  id: string
  venue: MarketVenueName
  venueTradeId: string
  price: number
  quantity: number
  fee: number
  feeAsset: string
  isMaker: boolean | null
  executedAt: string
}

export type ExchangeOrder = {
  id: string
  venue: MarketVenueName
  venueOrderId: string | null
  clientOrderId: string
  status: ExchangeOrderStatusName
  filledQuantity: number
  averageFillPrice: number | null
  requestHash: string | null
  responseHash: string | null
  submittedAt: string
  venueUpdatedAt: string | null
  lastReconciledAt: string | null
  fills: OrderFill[]
}

export type OrderIntent = {
  id: string
  botId: string
  strategyDecisionId: string
  operatingMode: OperatingModeName
  clientOrderId: string
  symbol: string
  direction: TradeDirectionName
  side: OrderSideName
  type: OrderTypeName
  quantity: number
  limitPrice: number | null
  takeProfitPrice: number | null
  stopLossPrice: number | null
  timeInForce: TimeInForceName | null
  referencePrice: number
  estimatedNotional: number
  status: OrderIntentStatusName
  statusReason: string | null
  submittedAt: string | null
  completedAt: string | null
  createdAt: string
  riskDecision: RiskDecision | null
  exchangeOrders: ExchangeOrder[]
}

/**
 * One link in the audit chain. Ordered by `occurredAt` *then* `sequence` — a tick writes several
 * events inside one transaction, so timestamps alone cannot order them.
 */
export type BotAuditEvent = {
  id: string
  botId: string | null
  operatingMode: OperatingModeName
  eventType: BotAuditEventTypeName
  correlationId: string
  sequence: number
  summary: string
  detailJson: string | null
  symbol: string | null
  candleOpenTime: string | null
  modelVersion: string | null
  strategyDecisionId: string | null
  orderIntentId: string | null
  riskDecisionId: string | null
  exchangeOrderId: string | null
  orderFillId: string | null
  botPositionId: string | null
  killSwitchId: string | null
  actorUserName: string | null
  occurredAt: string
}

// ─── Kill switches ────────────────────────────────────────────────────────────────────────────────

/**
 * Engaging blocks *new* intents. It does not cancel resting orders and it does not close positions —
 * cancelling a working stop-loss would leave an open position unprotected. The UI says this on the
 * confirmation, because "kill switch" reads like "flatten everything" and here it does not.
 */
export type KillSwitchInput = {
  scope: KillSwitchScopeName
  scopeOperatingMode?: OperatingModeName | null
  scopeVenue?: MarketVenueName | null
  scopeBotId?: string | null
  scopeSymbol?: string | null
  reason: string
}

export type KillSwitch = {
  id: string
  scope: KillSwitchScopeName
  scopeOperatingMode: OperatingModeName | null
  scopeVenue: MarketVenueName | null
  scopeBotId: string | null
  scopeSymbol: string | null
  isEngaged: boolean
  reason: string
  isAutomatic: boolean
  triggerDetail: string | null
  engagedAt: string | null
  engagedByUserName: string | null
  disengagedAt: string | null
  disengagedByUserName: string | null
  createdAt: string
}

// ─── Query shapes ─────────────────────────────────────────────────────────────────────────────────

/**
 * Trading listings page by *query parameter*, not by the `/{page}/{pageSize}/{desc}` path segments
 * the auth listings use. Two shapes in one client is a wart; inventing a third by making these look
 * like the others would be worse.
 */
export type TradingPageQuery = {
  pageNumber: number
  pageSize: number
}

export type BotFilters = {
  operatingMode?: OperatingModeName | ''
  status?: BotStatusName | ''
  symbol?: string
}

export type BotDecisionFilters = { action?: BotDecisionActionName | '' }
export type KillSwitchFilters = { engagedOnly?: boolean }

// ─── ML engine ────────────────────────────────────────────────────────────────────────────────────

/**
 * One market the engine has a model for.
 *
 * `isWildcard` true means this row is answered by the pooled cross-symbol model rather than a
 * dedicated fit. That is not a defect — every feature the model reads is scale-free, which is what
 * makes one estimator generalise to a pair it never saw — but it is a fact the reader is entitled to,
 * so it is reported rather than smoothed over.
 */
export type MlSupportedMarket = {
  symbol: string
  interval: string
  modelId: string
  modelVersion: string
  isWildcard: boolean
}

export type MlCapabilities = {
  service: string
  serviceVersion: string
  protocolVersion: string
  capabilities: string[]
  supportedOperations: string[]
  modelReady: boolean
  minimumCandles: number
  maximumCandles: number
  supportedMarkets: MlSupportedMarket[]
  wildcardModelReady: boolean
  operatingMode: string
}

/** One point on a model's measured confidence distribution: the share of held-out candles at or above a threshold. */
export type MlConfidenceReach = { threshold: number; share: number }

/**
 * Model metadata.
 *
 * `confidenceCeiling` is the highest confidence the model produced on held-out data, or `0` when the
 * training run did not measure it. A minimum-confidence floor above that ceiling can never be met, so
 * what it filters out is every signal — silence, not safety.
 */
export type ChartCandle = {
  openTime: string
  open: number
  high: number
  low: number
  close: number
}

export type MlModelInfo = {
  ready: boolean
  modelId: string
  modelVersion: string
  projectVersion: string
  symbol: string
  interval: string
  trainedAt: string | null
  featureCount: number
  isWildcard: boolean
  labelScheme: string
  calibrationMethod: string
  defaultMaxHoldingPeriods: number
  minimumBarrierAtr: number
  maximumBarrierAtr: number
  confidenceCeiling: number
  confidenceReach: MlConfidenceReach[]
}
