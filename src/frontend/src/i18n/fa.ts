/**
 * Every Persian string the dashboard renders, in one file.
 *
 * Not a translation layer — there is one locale, and inventing an i18n framework for it would be
 * ceremony. The point of collecting them here is that Persian copy is hard to review when it is
 * scattered through JSX: wording drifts, a term gets two translations, and a typo in an RTL string
 * inside a `className`-heavy component is nearly invisible. Grouped, they can be read as prose.
 *
 * Messages the API already writes in Persian are passed through untouched. Only the client's own
 * copy lives here, plus the status-code fallbacks for when the API sends no message at all.
 */

export const fa = {
  app: {
    name: 'کریپتو سیگنال',
    tagline: 'سامانه عملیات معاملاتی',
    shortName: 'CS',
  },

  common: {
    loading: 'در حال بارگذاری…',
    retry: 'تلاش دوباره',
    cancel: 'انصراف',
    save: 'ذخیره',
    close: 'بستن',
    optional: 'اختیاری',
    show: 'نمایش',
    hide: 'پنهان کردن',
    showPassword: 'نمایش کلمه عبور',
    hidePassword: 'پنهان کردن کلمه عبور',
    openMenu: 'باز کردن منو',
    closeMenu: 'بستن منو',
    comingSoon: 'در حال ساخت',

    create: 'ایجاد',
    edit: 'ویرایش',
    delete: 'حذف',
    confirm: 'تایید',
    refresh: 'بارگذاری دوباره',
    all: 'همه',
    active: 'فعال',
    inactive: 'غیرفعال',
    locked: 'قفل شده',
    saving: 'در حال ذخیره…',
    selectAll: 'انتخاب همه',
    clearAll: 'حذف همه',
    notSet: 'تعیین نشده',
    none: 'ندارد',
  },

  theme: {
    switchToDark: 'تغییر به حالت تاریک',
    switchToLight: 'تغییر به حالت روشن',
  },

  auth: {
    loginTitle: 'ورود به سامانه',
    loginSubtitle: 'برای دسترسی به داشبورد عملیات وارد شوید',
    registerTitle: 'ایجاد حساب کاربری',
    registerSubtitle: 'حساب شما پس از تایید مدیر سامانه فعال می‌شود',

    userName: 'نام کاربری',
    password: 'کلمه عبور',
    fullName: 'نام و نام خانوادگی',
    email: 'ایمیل',
    mobile: 'شماره همراه',
    confirmPassword: 'تکرار کلمه عبور',
    currentPassword: 'کلمه عبور فعلی',
    newPassword: 'کلمه عبور جدید',
    confirmNewPassword: 'تکرار کلمه عبور جدید',

    userNamePlaceholder: 'نام کاربری خود را وارد کنید',
    passwordPlaceholder: 'کلمه عبور خود را وارد کنید',
    fullNamePlaceholder: 'مثلا علی رضایی',
    emailPlaceholder: 'name@example.com',
    mobilePlaceholder: '09123456789',
    // Persian digits are accepted in the field and converted before the request; the server's
    // phone pattern only matches ASCII digits.
    mobileHint: 'ارقام فارسی هم پذیرفته می‌شود',

    submitLogin: 'ورود',
    submittingLogin: 'در حال ورود…',
    submitRegister: 'ثبت‌نام',
    submittingRegister: 'در حال ثبت‌نام…',
    submitChangePassword: 'تغییر کلمه عبور',
    submittingChangePassword: 'در حال تغییر کلمه عبور…',

    noAccount: 'حساب کاربری ندارید؟',
    goToRegister: 'ثبت‌نام کنید',
    haveAccount: 'حساب کاربری دارید؟',
    goToLogin: 'وارد شوید',
    backToLogin: 'بازگشت به صفحه ورود',

    logout: 'خروج از حساب',
    loggingOut: 'در حال خروج…',

    registerSuccessTitle: 'ثبت‌نام شما انجام شد',
    registerSuccessBody:
      'حساب کاربری شما ایجاد شد اما هنوز فعال نیست. مدیر سامانه پس از بررسی، دسترسی لازم را به شما اختصاص می‌دهد و از آن پس می‌توانید وارد شوید.',

    changePasswordTitle: 'تغییر کلمه عبور',
    changePasswordSubtitle: 'کلمه عبور جدیدی برای حساب خود انتخاب کنید',
    changePasswordForcedTitle: 'تغییر کلمه عبور الزامی است',
    changePasswordForcedBody:
      'برای این حساب کلمه عبور پیشفرض تنظیم شده است. پیش از دسترسی به داشبورد باید آن را تغییر دهید.',
    changePasswordSuccess: 'کلمه عبور شما با موفقیت تغییر کرد',

    // The change-password endpoint invalidates the security stamp, so the token in hand stops
    // working the moment the password changes — the user has to sign in again with the new one.
    changePasswordReLogin: 'برای ادامه، با کلمه عبور جدید دوباره وارد شوید',

    sessionExpired: 'نشست شما به پایان رسیده است. لطفا دوباره وارد شوید',
  },

  passwordRules: {
    title: 'کلمه عبور باید شامل موارد زیر باشد:',
    length: 'حداقل 8 کاراکتر',
    lower: 'یک حرف کوچک انگلیسی (a-z)',
    upper: 'یک حرف بزرگ انگلیسی (A-Z)',
    digit: 'یک رقم (0-9)',
    special: 'یک کاراکتر خاص',
    match: 'تکرار کلمه عبور با آن یکسان باشد',
  },

  /**
   * Client-side validation messages, worded **identically to the server's**.
   *
   * Transcribed verbatim from `RegisterDto.Validate` and `BaseChangePasswordDto.Validate` — Latin
   * digit `8` and all. The client pre-checks only the rules it can mirror exactly, so a user never
   * sees one sentence from the form and a differently-worded one for the same rule from the API.
   */
  validation: {
    userNameRequired: 'نام کاربری اجباری است',
    fullNameRequired: 'نام و نام خانوادگی اجباری است',
    passwordRequired: 'وارد نمودن کلمه عبور اجباری است',
    confirmPasswordRequired: 'وارد نمودن تکرار کلمه عبور اجباری است',
    newPasswordRequired: 'وارد نمودن کلمه عبور جدید اجباری است',
    confirmNewPasswordRequired: 'وارد نمودن تکرار کلمه جدید عبور اجباری است',
    passwordWeak:
      'کلمه عبور باید حداقل 8 کارکتر شامل یک کارکتر کوچک انگلیسی، یک کارکتر بزرگ انگلیسی، یک کارکتر خاص و عدد باشد',
    newPasswordWeak:
      'کلمه عبور جدید باید حداقل 8 کارکتر شامل یک کارکتر کوچک انگلیسی، یک کارکتر بزرگ انگلیسی، یک کارکتر خاص و عدد باشد',
    passwordMismatch: 'کلمه عبور و تکرار آن با یکدیگر مغایرت دارد',
    newPasswordMismatch: 'کلمه عبور جدید و تکرار آن با یکدیگر مغایرت دارد',

    // Worded to match `BaseUserInputDto.Validate` and `RoleInputDto.Validate` exactly, so a rule
    // caught here reads identically to the same rule caught on the server.
    emailInvalid: 'ایمیل نامعتبر است',
    phoneInvalid: 'تلفن نامعتبر است',
    mobileInvalid: 'شماره همراه نامعتبر است',
    personelCodeDigits: 'کد پرسنلی بایستی فقط شامل عدد باشد',
    rolesRequired: 'نقشی به کاربر اختصاص داده نشده است',
    roleNameRequired: 'وارد نمودن نام نقش اجباری است',
    roleNameTooLong: 'طول نام نقش حداکثر شامل 100 کارکتر می باشد',
    roleTitleRequired: 'وارد نمودن عنوان نقش اجباری است',
    roleTitleTooLong: 'طول عنوان نقش حداکثر شامل 100 کارکتر می باشد',
    permissionsRequired: 'هیچ مجوز دسترسی برای این نقش انتخاب نشده است',

    // Bot form — the fields whose blanks the server would turn into a denied trade or an unparseable
    // payload. Client-side wording matches `TradingBotInputDto.Validate`.
    botNameRequired: 'وارد کردن نام ربات اجباری است',
    botSymbolRequired: 'وارد کردن نماد اجباری است',
    botPercentPositive: 'درصد حد سود و ضرر باید عددی مثبت باشند',
    botNotionalPositive: 'ارزش هر سفارش باید عددی مثبت باشد',
  },

  nav: {
    overview: 'نمای کلی',
    signal: 'سیگنال لحظه‌ای',
    bots: 'ربات‌های معاملاتی',
    killSwitches: 'توقف اضطراری',
    connections: 'اتصالات صرافی',
    users: 'کاربران',
    roles: 'نقش‌ها',
    permissions: 'سطوح دسترسی',
    loginHistory: 'تاریخچه ورود',
    ml: 'موتور یادگیری ماشین',
    sectionMain: 'عملیات',
    sectionAdmin: 'مدیریت سامانه',
  },

  layout: {
    operatingMode: 'حالت اجرا',
    paperModeNote: 'هیچ سفارش واقعی به صرافی ارسال نمی‌شود',
    liveModeNote: 'سفارش‌ها به صرافی واقعی ارسال می‌شوند',
    superAdmin: 'مدیر ارشد سامانه',
    userMenu: 'منوی کاربر',
    sidebarLabel: 'منوی اصلی',
    skipToContent: 'رفتن به محتوای اصلی',
  },

  overview: {
    title: 'نمای کلی سامانه',
    subtitle: 'وضعیت سرویس‌ها، حالت اجرا و مرز اجرای سفارش',
    summaryLabel: 'خلاصه وضعیت',
    servicesLabel: 'سرویس‌های سامانه',
    orchestrator: 'هماهنگ‌کننده',
    orchestratorDetail: 'واسط برنامه‌نویسی دات‌نت 10',
    mlEngine: 'موتور یادگیری ماشین',
    mlEngineDetail: 'سرویس محاسباتی پایتون',
    database: 'پایگاه داده',
    databaseDetail: 'پستگرس‌کیوال 18',
    statusHealthy: 'سالم',
    statusUnhealthy: 'ناسالم',
    statusConnecting: 'در حال اتصال',
    modeCardLabel: 'حالت اجرا',
    servicesCardLabel: 'سرویس‌های سالم',
    servicesCardCaption: 'از سرویس‌های پایه سامانه',
    lastCheckLabel: 'آخرین بررسی سلامت',
    lastCheckPending: 'در انتظار پاسخ سرویس',
    boundaryLabel: 'مرز اجرای سفارش',
    boundaryFallback: 'تمام تصمیم‌های اجرای سفارش در اختیار هماهنگ‌کننده دات‌نت است',
    flowDashboard: 'داشبورد ری‌اکت',
    flowOrchestrator: 'هماهنگ‌کننده دات‌نت',
    flowExchange: 'واسط صرافی',
    flowMarketData: 'داده بازار',
    flowMl: 'یادگیری ماشین پایتون',
    flowSignalOnly: 'فقط سیگنال',
    unreachable: 'سرویس هماهنگ‌کننده در دسترس نیست',
    activeBotsLabel: 'ربات‌های فعال',
    activeBotsCaption: 'ربات‌های در حال اجرا از کل ربات‌ها',
    openPositionsLabel: 'پوزیشن‌های باز',
    openPositionsCaption: 'مجموع پوزیشن‌های باز همه ربات‌ها',
    blockedBotsLabel: 'کلید توقف اضطراری',
    blockedBotsZero: 'هیچ رباتی مسدود نیست',
    blockedBotsSome: 'ربات مسدود شده — سفارش جدید ثبت نمی‌شود',
    killSwitchBlockAlert: 'یک یا چند رباتِ فعال توسط کلید توقف اضطراری مسدود شده‌اند؛ تا رفع مسدودی، هیچ سفارش جدیدی ثبت نمی‌شود.',
    botsSectionLabel: 'ربات‌های در حال اجرا',
    botsSectionDetail: 'وضعیت لحظه‌ای ربات‌های فعال — نماد، حالت اجرا، اهرم و آخرین تیک هر کدام',
    botsEmptyTitle: 'هیچ ربات فعالی نیست',
    botsEmptyBody: 'یک ربات ایجاد کنید و آن را شروع کنید تا وضعیت زنده‌اش اینجا دیده شود.',
    botsLoadFailed: 'بارگذاری وضعیت ربات‌ها ناموفق بود',
    lastTickLabel: 'آخرین تیک',
    leverageUnit: 'اهرم ×',
    marketPulseLabel: 'نبض بازار',
    marketPulseDetail: 'کندل‌های ۱۵ دقیقه‌ای بازارِ نخستین ربات فعال — به‌روزرسانی خودکار',
    pnlByBotLabel: 'سود و زیان تحقق‌یافته هر ربات',
    pnlByBotDetail: 'ارقامِ محاسبه‌شده در سرور برای هر ربات، مقیاس میله‌ها نسبی است',
    pnlEmpty: 'هنوز معامله بسته‌ای ثبت نشده تا سود یا زیانی دیده شود',
    mlHealthLabel: 'سلامت موتور یادگیری ماشین',
    mlSampleLabel: 'حجم نمونه',
    mlWinsLabel: 'بردها',
    mlLossesLabel: 'باخت‌ها',
    mlAvgPnlLabel: 'میانگین سود هر معامله',
    mlTotalPnlLabel: 'مجموع سود تحقق‌یافته',
    calibrationLabel: 'کالیبراسیون اعتماد',
    calibrationDetail: 'در مدل سالم نرخ برد هر سطل با مرکز آن بالا می‌رود؛ الگوی تخت یا معکوس نخستین نشانه رانش مدل است',
    perSymbolLabel: 'به تفکیک نماد',
    tradesUnit: 'معامله',
  },

  /**
   * Vocabulary shared by every trading screen: the enum labels, and the words that appear on more
   * than one page.
   *
   * The enums arrive from the server as strings (`'Paper'`, `'Faulted'`, `'AdjustBracket'`), so each
   * map is keyed by the wire value and typed `Record<string, string>` — an unmapped value then renders
   * as the raw token instead of as `undefined`. That is the right failure: a new `BotStatus` shipped by
   * the server shows up as `Reconciling` in the table, which reads as a missing translation rather
   * than as a broken row.
   */
  trading: {
    // ── Operating mode. The single most important word on any bot screen.
    mode: {
      Paper: 'کاغذی',
      Sandbox: 'آزمایشی',
      Live: 'واقعی',
    } as Record<string, string>,

    modeNote: {
      Paper: 'سفارش‌ها فقط شبیه‌سازی می‌شوند و هیچ درخواستی به صرافی نمی‌رود',
      Sandbox: 'سفارش‌ها به شبکه آزمایشی صرافی می‌روند؛ دارایی واقعی درگیر نیست',
      Live: 'سفارش‌ها با دارایی واقعی در صرافی ثبت می‌شوند',
    } as Record<string, string>,

    venue: {
      Replay: 'بازپخش داده ضبط‌شده',
      BinanceTestnet: 'بایننس - شبکه آزمایشی',
      BinanceMainnet: 'بایننس - شبکه اصلی',
      Bitunix: 'بیت‌یونیکس',
      Bybit: 'بای‌بیت دمو',
    } as Record<string, string>,

    botStatus: {
      Draft: 'پیش‌نویس',
      Active: 'فعال',
      Paused: 'موقتا متوقف',
      Stopped: 'متوقف',
      Faulted: 'خطا',
    } as Record<string, string>,

    directionLabel: 'جهت پیشنهادی',
    closeReasonLabel: 'دلیل بستن موقعیت',
    direction: {
      Long: 'خرید',
      Short: 'فروش استقراضی',
      Flat: 'بدون موقعیت',
    } as Record<string, string>,

    action: {
      Hold: 'نگه‌داشتن',
      Open: 'باز کردن موقعیت',
      Close: 'بستن موقعیت',
      AdjustBracket: 'جابه‌جایی حد سود و ضرر',
    } as Record<string, string>,

    positionStatus: {
      Open: 'باز',
      Closed: 'بسته',
    } as Record<string, string>,

    orderSide: {
      Buy: 'خرید',
      Sell: 'فروش',
    } as Record<string, string>,

    orderType: {
      Market: 'بازار',
      Limit: 'محدود',
      StopLoss: 'حد ضرر',
      StopLossLimit: 'حد ضرر محدود',
      TakeProfit: 'حد سود',
      TakeProfitLimit: 'حد سود محدود',
    } as Record<string, string>,

    intentStatus: {
      Draft: 'پیش‌نویس',
      RiskApproved: 'تایید ریسک',
      RiskDenied: 'رد ریسک',
      Submitting: 'در حال ارسال',
      Submitted: 'ارسال شده',
      PartiallyFilled: 'اجرای جزئی',
      Filled: 'اجرا شده',
      Cancelled: 'لغو شده',
      Rejected: 'رد شده توسط صرافی',
      Expired: 'منقضی شده',
      Ambiguous: 'وضعیت نامشخص',
    } as Record<string, string>,

    orderStatus: {
      New: 'ثبت شده',
      PartiallyFilled: 'اجرای جزئی',
      Filled: 'اجرا شده',
      Cancelled: 'لغو شده',
      Rejected: 'رد شده',
      Expired: 'منقضی شده',
      PendingCancel: 'در انتظار لغو',
      Unknown: 'نامشخص',
    } as Record<string, string>,

    closeReason: {
      TakeProfitTouched: 'برخورد با حد سود',
      StopLossTouched: 'برخورد با حد ضرر',
      MaxHoldingPeriodsReached: 'پایان مدت نگهداری',
      DirectionReversed: 'برگشت جهت پیش‌بینی',
      ManualClose: 'بستن دستی',
      KillSwitch: 'توقف اضطراری',
      BotStopped: 'توقف ربات',
      Liquidation: 'تسویه اجباری',
    } as Record<string, string>,

    killSwitchScope: {
      Global: 'کل سامانه',
      OperatingMode: 'یک حالت اجرا',
      Exchange: 'یک صرافی',
      Bot: 'یک ربات',
      Symbol: 'یک نماد',
    } as Record<string, string>,

    auditEvent: {
      CandleWindowRecorded: 'ثبت پنجره کندل',
      ModelConsulted: 'پرس‌وجو از مدل',
      DecisionRecorded: 'ثبت تصمیم',
      IntentCreated: 'ایجاد قصد سفارش',
      RiskEvaluated: 'ارزیابی ریسک',
      OrderSubmitted: 'ارسال سفارش',
      OrderAcknowledged: 'تایید سفارش توسط صرافی',
      OrderRejected: 'رد سفارش توسط صرافی',
      FillRecorded: 'ثبت اجرا',
      PositionOpened: 'باز شدن موقعیت',
      PositionUpdated: 'به‌روزرسانی موقعیت',
      PositionClosed: 'بسته شدن موقعیت',
      KillSwitchEngaged: 'فعال شدن توقف اضطراری',
      BotFaulted: 'خطای ربات',
      ConfigurationChanged: 'تغییر تنظیمات',
    } as Record<string, string>,

    /**
     * The engine's `reason_code`, in words.
     *
     * One token from a fixed vocabulary — the orchestrator switches on it, so it is the one part of the
     * engine's answer that is safe to translate. The prose in `warning` is not: it is advisory text
     * that may change wording between engine versions, so it is displayed verbatim.
     */
    reasonCode: {
      no_edge: 'برتری آماری کافی وجود ندارد',
      confidence_below_minimum: 'اطمینان مدل کمتر از حد تعیین شده است',
      short_not_allowed: 'فروش استقراضی برای این ربات مجاز نیست',
      take_profit_touched: 'قیمت به حد سود رسید',
      stop_loss_touched: 'قیمت به حد ضرر رسید',
      max_holding_periods_reached: 'مدت مجاز نگهداری موقعیت پایان یافت',
      direction_reversed: 'جهت پیش‌بینی مدل برگشت',
      trailing_stop_advanced: 'حد ضرر متحرک جابه‌جا شد',
    } as Record<string, string>,

    /**
     * The pre-trade checks, named as the risk engine names them.
     *
     * Kept in sync with `RiskCheck`'s `[Display(Name)]` values by hand. A missing entry falls back to
     * the English member name, which is still readable and still identifies the check.
     */
    riskCheck: {
      ModeAndStrategyEnabled: 'فعال بودن حالت اجرا و استراتژی',
      ModelVersionApproved: 'تایید نسخه مدل',
      SignalProvenance: 'اصالت سیگنال',
      SignalNotAlreadyActedOn: 'اقدام نشدن قبلی روی این سیگنال',
      DataFreshness: 'تازگی داده بازار',
      MarketAllowlistedAndTradable: 'مجاز و قابل معامله بودن نماد',
      OrderParametersSupported: 'پشتیبانی از پارامترهای سفارش',
      NotionalWithinBounds: 'ارزش سفارش در محدوده مجاز',
      ExposureWithinLimits: 'حجم موقعیت باز در محدوده مجاز',
      LossAndDrawdownWithinLimits: 'زیان و افت سرمایه در محدوده مجاز',
      FrequencyAndTurnoverWithinLimits: 'تعداد سفارش در محدوده مجاز',
      SufficientBalance: 'کفایت موجودی',
      ConnectivityAndReconciliationHealthy: 'سلامت اتصال و مغایرت‌گیری',
      KillSwitchesClear: 'غیرفعال بودن توقف اضطراری',
      HumanApprovalValid: 'اعتبار تایید انسانی',
      BarrierWithinFittedRange: 'قرار گرفتن حد سود و ضرر در دامنه آموزش مدل',
    } as Record<string, string>,

    // ── Words shared by more than one screen.
    symbol: 'نماد',
    interval: 'تایم‌فریم',
    venueLabel: 'منبع داده',
    modeLabel: 'حالت اجرا',
    takeProfit: 'حد سود',
    stopLoss: 'حد ضرر',
    takeProfitPercent: 'درصد حد سود',
    stopLossPercent: 'درصد حد ضرر',
    entryPrice: 'قیمت ورود',
    takeProfitPrice: 'قیمت حد سود',
    stopLossPrice: 'قیمت حد ضرر',
    allowShort: 'اجازه فروش استقراضی',
    confidence: 'اطمینان مدل',
    minimumConfidence: 'حداقل اطمینان',
    expectedValue: 'ارزش مورد انتظار',
    riskReward: 'نسبت سود به ریسک',
    atr: 'میانگین دامنه واقعی',
    model: 'مدل',
    modelVersion: 'نسخه مدل',
    quantity: 'مقدار',
    price: 'قیمت',
    notional: 'ارزش',
    pnl: 'سود و زیان',
    realizedPnl: 'سود و زیان محقق شده',
    unrealizedPnl: 'سود و زیان باز',
    fees: 'کارمزد',
    candleTime: 'زمان کندل',
    validUntil: 'اعتبار تا',
    expired: 'منقضی شده',
    pooledModel: 'مدل مشترک',
    pooledModelNote: 'این پاسخ از مدل مشترک چندنمادی آمده، نه از مدلی که فقط روی این نماد آموزش دیده باشد',
    extrapolated: 'فراتر از دامنه آموزش',
    extrapolatedNote:
      'فاصله حد سود یا حد ضرر درخواستی بیرون از دامنه‌ای است که مدل روی آن آموزش دیده. ارزش مورد انتظار در این حالت برآورد است، نه اندازه‌گیری.',
    killSwitchBlocked: 'مسدود شده با توقف اضطراری',

    /**
     * The line every screen that shows a signal or a bot carries.
     *
     * Not decoration. A probability is evidence about what a market might do; the decision to place an
     * order is a separate act with its own authorization, and it never happens in the browser.
     */
    evidenceNote: 'سیگنال یک شاهد آماری است، نه مجوز سفارش. هیچ کنترلی در این داشبورد سفارشی را به صرافی ارسال نمی‌کند.',
  },

  signal: {
    title: 'سیگنال لحظه‌ای',
    subtitle: 'یک پاسخ کالیبره‌شده برای یک نماد و یک شرط سود و ضرر مشخص',

    formLabel: 'پارامترهای درخواست',
    submit: 'دریافت سیگنال',
    submitting: 'در حال محاسبه…',

    symbolHint: 'نماد بازار اسپات بایننس، مثلا BTCUSDT',
    intervalHint: 'دوره هر کندل',
    takeProfitHint: 'درصد سود هدف نسبت به قیمت ورود',
    stopLossHint: 'درصد زیان قابل تحمل نسبت به قیمت ورود',
    allowShortHint: 'اگر خاموش باشد، اطمینان سمت فروش هم گزارش می‌شود اما جهت پیشنهادی هرگز فروش نخواهد بود',
    maxHoldingHint: 'حداکثر تعداد کندلی که موقعیت نگه داشته می‌شود. خالی بماند، مقدار پیشفرض موتور استفاده می‌شود.',
    minimumConfidenceHint: 'زیر این حد، پاسخ «بدون موقعیت» است. خالی بماند، مقدار پیشفرض موتور استفاده می‌شود.',
    advanced: 'تنظیمات پیشرفته',

    // The candle window is fetched server-side on purpose; saying so is part of the audit story.
    candleSourceNote:
      'پنجره کندل توسط سرور از منبع داده انتخاب شده خوانده می‌شود؛ مرورگر هیچ داده قیمتی به مدل نمی‌فرستد.',

    emptyTitle: 'هنوز درخواستی ثبت نشده',
    emptyBody: 'نماد، تایم‌فریم و درصد سود و ضرر خود را وارد کنید تا موتور یادگیری ماشین پاسخ بدهد.',

    resultLabel: 'پاسخ موتور',
    flatTitle: 'پیشنهادی برای ورود وجود ندارد',
    flatBody: 'با این شرط سود و ضرر، مدل موقعیتی را با اطمینان کافی پیشنهاد نمی‌کند.',

    longSide: 'سمت خرید',
    shortSide: 'سمت فروش',
    probabilityLabel: 'احتمال هر خروج',
    probTakeProfit: 'رسیدن به حد سود',
    probStopLoss: 'رسیدن به حد ضرر',
    probTimeout: 'پایان مدت بدون برخورد',
    barrierAtr: 'فاصله بر حسب دامنه واقعی',
    candleCount: 'تعداد کندل بررسی شده',
    processing: 'زمان محاسبه',
    digest: 'اثر انگشت ورودی',
    rationale: 'دلایل مدل',
    engineWarning: 'هشدار موتور',
    validityRemaining: 'اعتبار باقی‌مانده',
    validityExpired: 'اعتبار این سیگنال پایان یافته است. کندل بعدی بسته شده و پاسخ باید دوباره گرفته شود.',
    milliseconds: 'میلی‌ثانیه',
    candles: 'کندل',
  },

  bots: {
    title: 'ربات‌های معاملاتی',
    subtitle: 'تنظیم ربات، اجرای خودکار خرید و فروش، و زنجیره کامل تصمیم تا اجرا',

    createButton: 'ربات جدید',
    createTitle: 'ساخت ربات جدید',
    editTitle: 'ویرایش ربات',

    colBot: 'ربات',
    colMarket: 'بازار',
    colMode: 'حالت',
    colStatus: 'وضعیت',
    colPosition: 'موقعیت باز',
    colPnl: 'سود و زیان محقق شده',
    colLastTick: 'آخرین بررسی',

    filterSymbol: 'جست‌وجو در نماد',
    filterStatus: 'وضعیت ربات',
    filterMode: 'حالت اجرا',

    emptyTitle: 'رباتی ساخته نشده است',
    emptyBody: 'یک ربات با نماد، تایم‌فریم و سقف‌های ریسک خودش بسازید. ربات تازه در وضعیت پیش‌نویس می‌ماند تا آن را اجرا کنید.',

    openPositions: 'موقعیت باز',
    noOpenPosition: 'بدون موقعیت باز',
    neverTicked: 'هنوز اجرا نشده',

    // ── Form
    sectionIdentity: 'شناسه ربات',
    sectionMarket: 'بازار و منبع داده',
    sectionStrategy: 'شرط سود و ضرر',
    sectionLimits: 'سقف‌های ریسک',

    name: 'نام ربات',
    nameHint: 'نامی که در فهرست و در سابقه دیده می‌شود',
    description: 'توضیح',

    marketLocked: 'نماد، تایم‌فریم، منبع داده و حالت اجرا پس از ساخت ربات قابل تغییر نیستند',
    quoteNotionalPerTrade: 'ارزش هر سفارش',
    quoteNotionalHint: 'به تتر. ارزش هر سفارشی که این ربات ثبت می‌کند.',
    maxHoldingPeriods: 'حداکثر مدت نگهداری',
    maxHoldingPeriodsHint: 'بر حسب تعداد کندل',
    cadenceSeconds: 'فاصله بررسی',
    cadenceSecondsHint: 'به ثانیه. ربات زودتر از این فاصله دوباره بررسی نمی‌شود.',
    expectedModelVersion: 'نسخه مدل مورد انتظار',
    expectedModelVersionHint: 'خالی بماند، هر نسخه‌ای پذیرفته می‌شود. پر شود، پاسخ مدل دیگری رد می‌شود.',

    maxOrderNotional: 'سقف ارزش هر سفارش',
    maxPositionNotional: 'سقف ارزش موقعیت باز',
    maxDailyLoss: 'سقف زیان روزانه',
    maxDrawdown: 'سقف افت سرمایه',
    maxConcurrentPositions: 'سقف موقعیت‌های هم‌زمان',
    maxOrdersPerDay: 'سقف سفارش در روز',
    maxConsecutiveFailures: 'سقف خطاهای پشت سر هم',
    maxSlippageBps: 'سقف لغزش قیمت',
    maxSlippageBpsHint: 'بر حسب صدم درصد',

    /**
     * The inversion, stated where the operator sets the numbers.
     *
     * This is the one thing about the form that is genuinely counter-intuitive: an empty limit field is
     * not "no limit", it is "no trade". Saying it once, next to the fields, is cheaper than a support
     * conversation about a bot that ticks and never orders.
     */
    limitsNote:
      'هر سقفی که صفر یا خالی بماند، به معنای «بدون محدودیت» نیست؛ به معنای «اجازه ندادن» است. سقف موثر، سخت‌گیرانه‌ترین مقدار بین سقف ربات و سقف سامانه است.',

    // ── Status changes
    start: 'اجرای ربات',
    pause: 'توقف موقت',
    stop: 'توقف کامل',
    reason: 'دلیل',
    reasonHint: 'در سابقه ربات ثبت می‌شود',
    reasonRequired: 'وارد کردن دلیل اجباری است',

    confirmStartTitle: 'اجرای ربات',
    confirmStartBody:
      'از این پس ربات در هر دوره، بازار را بررسی می‌کند و در صورت تایید موتور ریسک، سفارش ثبت خواهد کرد.',
    confirmPauseTitle: 'توقف موقت ربات',
    confirmPauseBody: 'بررسی دوره‌ای متوقف می‌شود. موقعیت‌های باز بسته نمی‌شوند و سفارش‌های ثبت‌شده لغو نمی‌شوند.',
    confirmStopTitle: 'توقف کامل ربات',
    confirmStopBody: 'ربات دیگر بررسی نمی‌شود و سفارش تازه‌ای ثبت نمی‌کند. موقعیت‌های باز و سفارش‌های فعال دست‌نخورده می‌مانند.',
    confirmDeleteTitle: 'حذف ربات',
    confirmDeleteBody: 'این ربات از فهرست حذف می‌شود. سابقه تصمیم‌ها و سفارش‌های آن برای حسابرسی باقی می‌ماند.',
    deleteBot: 'حذف ربات',

    createdSuccess: 'ربات جدید ساخته شد',
    updatedSuccess: 'تنظیمات ربات ذخیره شد',
    startedSuccess: 'ربات اجرا شد',
    pausedSuccess: 'ربات موقتا متوقف شد',
    stoppedSuccess: 'ربات متوقف شد',
    deletedSuccess: 'ربات حذف شد',
  },

  botDetail: {
    back: 'بازگشت به فهرست ربات‌ها',
    notFound: 'این ربات پیدا نشد',

    tabOverview: 'وضعیت',
    tabDecisions: 'تصمیم‌ها',
    tabOrders: 'سفارش‌ها',
    tabPositions: 'موقعیت‌ها',
    tabAudit: 'زنجیره حسابرسی',

    runLabel: 'اجرای جاری',
    noRun: 'اجرای فعالی وجود ندارد',
    leaseOwner: 'مالک اجرا',
    startedAt: 'شروع',
    lastHeartbeat: 'آخرین ضربان',
    tickCount: 'تعداد بررسی',
    decisionCount: 'تعداد تصمیم',
    orderCount: 'تعداد سفارش',
    errorCount: 'تعداد خطا',
    consecutiveFailures: 'خطاهای پشت سر هم',
    lastError: 'آخرین خطا',
    faultedAt: 'زمان بروز خطا',
    statusReason: 'دلیل وضعیت',

    limitsLabel: 'سقف‌های ریسک این ربات',
    strategyLabel: 'شرط سود و ضرر',
    configLabel: 'تنظیمات',

    positionsLabel: 'موقعیت‌های باز',
    noPositions: 'موقعیت بازی وجود ندارد',
    closedPositionCount: 'موقعیت بسته شده',
    barsHeld: 'کندل نگه داشته شده',
    averageEntry: 'میانگین قیمت ورود',
    averageExit: 'میانگین قیمت خروج',
    markPrice: 'قیمت لحظه‌ای',
    maxAdverseExcursion: 'بیشترین زیان میان‌راه',
    openedAt: 'زمان باز شدن',
    closedAt: 'زمان بسته شدن',

    decisionsLabel: 'تصمیم‌های ربات',
    decisionsEmptyTitle: 'تصمیمی ثبت نشده است',
    decisionsEmptyBody: 'ربات هنوز کندل بسته‌ای را بررسی نکرده، یا در وضعیت پیش‌نویس است.',
    colAction: 'تصمیم',
    colReason: 'دلیل',
    colLevels: 'حدها',
    colCandle: 'کندل',

    ordersLabel: 'قصد سفارش‌ها و اجرای آن‌ها',
    ordersEmptyTitle: 'سفارشی ثبت نشده است',
    ordersEmptyBody: 'هیچ قصد سفارشی برای این ربات ساخته نشده. رد شدن در موتور ریسک هم اینجا ثبت می‌شود.',
    riskLabel: 'ارزیابی ریسک',
    riskAllowed: 'مجاز',
    riskDenied: 'رد شده',
    failedChecks: 'بررسی‌های ناموفق',
    clientOrderId: 'شناسه سفارش',
    venueOrderId: 'شناسه صرافی',
    fills: 'اجراها',
    noFills: 'اجرایی ثبت نشده',
    snapshot: 'وضعیت ثبت‌شده هنگام ارزیابی',

    positionsEmptyTitle: 'موقعیتی ثبت نشده است',
    positionsEmptyBody: 'این ربات هنوز موقعیتی باز نکرده است.',

    auditLabel: 'زنجیره حسابرسی',
    auditEmptyTitle: 'رویدادی ثبت نشده است',
    auditEmptyBody: 'زنجیره حسابرسی با نخستین بررسی بازار پر می‌شود.',
    colEvent: 'رویداد',
    colSequence: 'ترتیب',
    colSummary: 'شرح',
    colOccurredAt: 'زمان',
    correlationId: 'شناسه همبستگی',
    actor: 'عامل',
    actorSystem: 'سامانه',

    killSwitchLabel: 'توقف اضطراری این ربات',
    engageForBot: 'توقف اضطراری این ربات',
  },

  killSwitches: {
    title: 'توقف اضطراری',
    subtitle: 'مسدود کردن ثبت سفارش تازه، در دامنه‌ای که انتخاب می‌کنید',

    /**
     * The scope of the switch, in the words that matter.
     *
     * Engaging blocks *new* order intents. It does not cancel a resting order and it does not close an
     * open position — an operator who believes otherwise will engage the switch and then wonder why
     * their position is still there.
     */
    scopeNote:
      'فعال کردن این کلید، جلوی ثبت سفارش تازه را می‌گیرد. سفارش‌های در جریان لغو نمی‌شوند و موقعیت‌های باز بسته نمی‌شوند؛ برای آن‌ها باید ربات را متوقف و موقعیت را دستی مدیریت کنید.',

    engageButton: 'فعال کردن توقف',
    engageTitle: 'فعال کردن توقف اضطراری',
    disengageTitle: 'غیرفعال کردن توقف اضطراری',
    disengage: 'غیرفعال کردن',

    colScope: 'دامنه',
    colState: 'وضعیت',
    colReason: 'دلیل',
    colEngagedBy: 'فعال شده توسط',
    colEngagedAt: 'زمان فعال‌سازی',

    filterEngagedOnly: 'فقط کلیدهای فعال',

    emptyTitle: 'کلید توقفی ثبت نشده است',
    emptyBody: 'هیچ توقف اضطراری‌ای در سامانه ثبت نشده. این یعنی هیچ دامنه‌ای مسدود نیست.',

    scope: 'دامنه',
    scopeHint: 'هر چه دامنه بسته‌تر، اثر کلید محدودتر',
    scopeModeField: 'حالت اجرا',
    scopeVenueField: 'صرافی',
    scopeBotField: 'شناسه ربات',
    scopeSymbolField: 'نماد',
    reason: 'دلیل',
    reasonHint: 'در سابقه ثبت می‌شود و در صفحه ربات دیده خواهد شد',
    reasonRequired: 'وارد کردن دلیل اجباری است',
    disengageReason: 'دلیل غیرفعال‌سازی',
    disengageReasonHint: 'به شرح رویداد اضافه می‌شود؛ دلیل اولیه فعال‌سازی دست‌نخورده می‌ماند',

    stateEngaged: 'فعال',
    stateDisengaged: 'غیرفعال',
    automatic: 'خودکار',
    automaticNote: 'این کلید را خود سامانه فعال کرده است',
    manual: 'دستی',
    triggerDetail: 'شرح رویداد',
    disengagedAt: 'زمان غیرفعال‌سازی',
    disengagedBy: 'غیرفعال شده توسط',

    confirmEngageTitle: 'فعال کردن توقف اضطراری',
    confirmEngageBody: 'تا زمانی که این کلید فعال است، در دامنه انتخاب شده هیچ سفارش تازه‌ای ثبت نمی‌شود.',
    confirmDisengageTitle: 'غیرفعال کردن توقف اضطراری',
    confirmDisengageBody: 'با غیرفعال شدن این کلید، ربات‌های دامنه انتخاب شده می‌توانند دوباره سفارش ثبت کنند.',

    engagedSuccess: 'توقف اضطراری فعال شد',
    disengagedSuccess: 'توقف اضطراری غیرفعال شد',
  },

  connections: {
    title: 'اتصالات صرافی',
    subtitle: 'کلیدهای API صرافی‌ها؛ ربات‌ها از اینجا مجوز معامله می‌گیرند',

    createButton: 'اتصال جدید',
    editTitle: 'ویرایش اتصال',
    createTitle: 'اتصال جدید',

    securityNote:
      'کلیدها روی سرور رمزنگاری و ذخیره می‌شوند و هرگز دوباره نمایش داده نمی‌شوند. فقط چهار کاراکتر آخر کلید برای تشخیص دیده می‌شود.',

    colLabel: 'نام اتصال',
    colState: 'وضعیت',
    stateActive: 'فعال',
    stateInactive: 'غیرفعال',
    colValidated: 'آخرین تایید صرافی',
    neverValidated: 'تایید نشده',

    apiKey: 'کلید API',
    apiSecret: 'مقدار مخفی API',
    apiSecretHint: 'رمزنگاری‌شده ذخیره می‌شود؛ هرگز نمایش داده نمی‌شود',
    labelHint: 'مثلا «حساب اصلی» برای تشخیص در فهرست',
    reenterHint: 'برای ویرایش، هر دو مقدار باید دوباره وارد شوند',
    labelRequired: 'وارد کردن نام اتصال اجباری است',
    secretsRequired: 'وارد کردن کلید و مقدار مخفی اجباری است',

    writeOnceNote:
      'این مقادیر پس از ذخیره قابل مشاهده نیستند. اگر اشتباه وارد شده باشند، باید دوباره از صرافی کپی شوند.',

    activate: 'فعال کردن',
    deactivate: 'غیرفعال کردن',
    confirmActivateTitle: 'فعال کردن این اتصال',
    confirmActivateBody: 'ربات‌هایی که به این اتصال متصل هستند دوباره می‌توانند سفارش ثبت کنند.',
    confirmDeactivateTitle: 'غیرفعال کردن این اتصال',
    confirmDeactivateBody:
      'از همین لحظه هیچ سفارشی با این کلید ثبت نمی‌شود. ربات‌های متصل به آن تا فعال شدن دوباره خطا می‌گیرند.',
    confirmDeleteTitle: 'حذف اتصال',
    confirmDeleteBody: 'این اتصال حذف می‌شود. ربات‌های متصل به آن باید به اتصال دیگری متصل شوند.',
    activatedSuccess: 'اتصال فعال شد',
    deactivatedSuccess: 'اتصال غیرفعال شد',
    createdSuccess: 'اتصال جدید ذخیره شد',
    updatedSuccess: 'اتصال به‌روزرسانی شد',
    deletedSuccess: 'اتصال حذف شد',

    pinLabel: 'اتصال صرافی این ربات',
    pinHint: 'خالی بماند، کلید سرور استفاده می‌شود',
    pinNone: 'کلید سرور (پیشفرض)',

    emptyTitle: 'اتصالی ثبت نشده است',
    emptyBody: 'برای معامله در یک صرافی، کلید API همان صرافی را اینجا ثبت کنید.',
  },

  monitor: {
    title: 'پایش زنده',
    heartbeatLive: 'زنده',
    heartbeatStale: 'کند شده',
    heartbeatDead: 'بی‌پاسخ',
    heartbeatIdle: 'غیرفعال',
    positionLabel: 'موقعیت باز',
    noPosition: 'موقعیتی باز نیست — ربات منتظر سیگنال با اطمینان کافی است',
    realizedPnl: 'سود و زیان محقق شده',
    lastCandle: 'آخرین کندل بررسی‌شده',
    alertsLabel: 'رویدادهای هشدار',
    decisionsLabel: 'جریان تصمیم‌ها',
    decidedAt: 'زمان تصمیم',
    noDecisions: 'هنوز تصمیمی ثبت نشده است',
    markedAt: 'آخرین قیمت‌گذاری',
    staleTitle: 'ضربان کند شده است',
    staleBody: (s: number) => `آخرین بررسی ربات ${s} ثانیه پیش بوده و از فاصله معمول بیشتر است.`,
    deadTitle: 'ربات بی‌پاسخ است',
    deadBody: (s: number) => `آخرین بررسی ${s} ثانیه پیش بوده است. اگر چند دقیقه دیگر برنگشت، لاگ سرور را بررسی کنید.`,
    priceLabel: 'قیمت لحظه‌ای',
    intervalLabel: 'بازه نمودار',
    confidenceTrendLabel: 'روند اطمینان مدل',
    confidenceTrendNote: 'هر نقطه یک تصمیم است؛ خط‌چین حداقل اطمینان ربات است. نقاط زیر خط‌چین یعنی مدل عمداً معامله نکرده.',
    calibrationChartLabel: 'نرخ برد مشاهده‌شده در هر بازه اطمینان',
    outcomesLabel: 'یادگیری مدل — پیش‌بینی در برابر نتیجه',
    modelTrained: 'آموزش دیده',
    trainedTitle: 'زمان آخرین آموزش مدل',
    newerModelTitle: 'مدل جدیدتر موجود است',
    newerModelBody: 'موتور اکنون مدلی جدیدتر از مدل تصمیم‌های اخیر این ربات در اختیار دارد. تصمیم‌های بعدی با مدل جدید ثبت می‌شوند.',
    modelStamp: 'مدل فعال',
    modelStampTitle: 'نسخه مدل تصمیم‌گیرنده',
    outcomesNote: 'از موقعیت‌های بسته‌شده: آیا اطمینان اعلامی مدل با نتیجه واقعی هم‌راستا بوده است؟',
    sampleSize: 'تعداد معاملات',
    winRate: 'نرخ برد',
    totalPnl: 'سود و زیان کل',
    avgPnl: 'میانگین هر معامله',
    bucket: 'بازه اطمینان',
    tradesCol: 'معاملات',
    winRateCol: 'نرخ برد مشاهده‌شده',
    pnlCol: 'سود و زیان',

    faultedTitle: 'ربات در وضعیت خطا است',
    faultedBody: 'اجرای ربات متوقف شده؛ دلیل آن در رویدادهای حسابرسی ثبت شده است.',
  },

  placeholder: {
    title: 'این بخش هنوز ساخته نشده است',
    body: 'زیرساخت احراز هویت و چیدمان داشبورد آماده است. این صفحه در گام‌های بعدی تکمیل می‌شود.',
  },

  /** Shared table chrome: the pager, the filter bar, and the states a listing can be in. */
  table: {
    createdAt: 'تاریخ ایجاد',
    rowsPerPage: 'تعداد در صفحه',
    noRecords: 'موردی برای نمایش نیست',
    // Assembled around Latin numerals as «۱ تا ۱۰ از ۶۲»; the spaces are part of the strings so the
    // numbers can each be wrapped in an isolating span without the gaps collapsing.
    rangeSeparator: ' تا ',
    rangeOf: ' از ',
    previousPage: 'صفحه قبل',
    nextPage: 'صفحه بعد',
    actions: 'عملیات',
    filters: 'فیلترها',
    clearFilters: 'حذف فیلترها',
    createdOn: 'تاریخ ایجاد',
    createdBy: 'ایجاد شده توسط',
    loadFailed: 'دریافت اطلاعات با خطا مواجه شد',
  },

  users: {
    title: 'کاربران',
    subtitle: 'مدیریت حساب‌های کاربری، نقش‌ها و وضعیت دسترسی به سامانه',

    createButton: 'کاربر جدید',
    createTitle: 'ایجاد کاربر جدید',
    editTitle: 'ویرایش کاربر',

    colUser: 'کاربر',
    colRoles: 'نقش‌ها',
    colType: 'نوع کاربری',
    colStatus: 'وضعیت',
    colContact: 'اطلاعات تماس',

    filterUserName: 'جست‌وجو در نام کاربری',
    filterFullName: 'جست‌وجو در نام و نام خانوادگی',
    filterStatus: 'وضعیت حساب',
    filterType: 'نوع کاربری',

    emptyTitle: 'کاربری یافت نشد',
    emptyBody: 'با فیلترهای فعلی هیچ حساب کاربری پیدا نشد. فیلترها را تغییر دهید یا کاربر جدیدی بسازید.',

    fullName: 'نام و نام خانوادگی',
    userName: 'نام کاربری',
    email: 'ایمیل',
    phone: 'تلفن ثابت',
    mobile: 'شماره همراه',
    personelCode: 'کد پرسنلی',
    address: 'نشانی',
    parent: 'کاربر بالادست',
    parentNone: 'بدون کاربر بالادست',
    userType: 'نوع کاربری',
    roles: 'نقش‌های کاربر',
    rolesHint: 'حداقل یک نقش باید انتخاب شود',
    rolesEmpty: 'هنوز نقشی در سامانه تعریف نشده است',
    noRoles: 'بدون نقش',

    userNameLocked: 'نام کاربری پس از ایجاد حساب قابل تغییر نیست',

    // The create form has no password field: the server hashes its own default and flags the account
    // for a forced change, so there is nothing for the operator to choose or to communicate.
    defaultPasswordNotice:
      'کلمه عبور این حساب به صورت خودکار روی مقدار پیشفرض سامانه تنظیم می‌شود و کاربر در نخستین ورود باید آن را تغییر دهد.',

    systemAccount: 'حساب سیستمی',
    systemAccountNote: 'این حساب توسط سامانه ساخته شده و قابل ویرایش، حذف یا غیرفعال‌سازی نیست',

    activate: 'فعال‌سازی حساب',
    deactivate: 'غیرفعال‌سازی حساب',
    resetPassword: 'بازیابی کلمه عبور',
    deleteUser: 'حذف کاربر',

    confirmActivateTitle: 'فعال‌سازی حساب کاربری',
    confirmActivateBody: 'با این کار حساب کاربری فعال شده، قفل آن برداشته می‌شود و کاربر می‌تواند وارد سامانه شود.',
    confirmDeactivateTitle: 'غیرفعال‌سازی حساب کاربری',
    confirmDeactivateBody: 'با این کار کاربر دیگر نمی‌تواند وارد سامانه شود. نشست‌های فعال او نیز باطل می‌شود.',
    confirmResetTitle: 'بازیابی کلمه عبور',
    confirmResetBody:
      'کلمه عبور این کاربر به مقدار پیشفرض سامانه بازمی‌گردد و در نخستین ورود باید آن را تغییر دهد. نشست‌های فعال او باطل می‌شود.',
    confirmDeleteTitle: 'حذف کاربر',
    confirmDeleteBody: 'این حساب کاربری از فهرست حذف می‌شود. این عمل قابل بازگشت نیست.',

    createdSuccess: 'کاربر جدید با موفقیت ایجاد شد',
    updatedSuccess: 'اطلاعات کاربر با موفقیت ذخیره شد',
    activatedSuccess: 'حساب کاربری فعال شد',
    deactivatedSuccess: 'حساب کاربری غیرفعال شد',
    resetSuccess: 'کلمه عبور کاربر به مقدار پیشفرض بازگشت',
    deletedSuccess: 'کاربر حذف شد',
  },

  roles: {
    title: 'نقش‌ها',
    subtitle: 'تعریف نقش‌ها و تخصیص سطوح دسترسی به هر نقش',

    createButton: 'نقش جدید',
    createTitle: 'ایجاد نقش جدید',
    editTitle: 'ویرایش نقش',

    colRole: 'نقش',
    colType: 'نوع',
    colPermissions: 'سطوح دسترسی',

    filterTitle: 'جست‌وجو در عنوان نقش',

    emptyTitle: 'نقشی یافت نشد',
    emptyBody: 'با فیلتر فعلی نقشی پیدا نشد. فیلتر را تغییر دهید یا نقش جدیدی تعریف کنید.',

    name: 'نام نقش',
    nameHint: 'شناسه انگلیسی نقش، مثلا Analyst',
    roleTitle: 'عنوان نقش',
    roleTitleHint: 'عنوانی که در سامانه نمایش داده می‌شود',
    permissions: 'سطوح دسترسی',
    permissionsHint: 'حداقل یک سطح دسترسی باید انتخاب شود',
    permissionCount: 'سطح دسترسی',
    noPermissions: 'بدون سطح دسترسی',

    systemRole: 'نقش سیستمی',
    systemRoleNote: 'این نقش پیشفرض سامانه است و قابل ویرایش یا حذف نیست',

    deleteRole: 'حذف نقش',
    confirmDeleteTitle: 'حذف نقش',
    confirmDeleteBody: 'این نقش حذف می‌شود. کاربرانی که تنها همین نقش را دارند دسترسی خود را از دست می‌دهند.',

    createdSuccess: 'نقش جدید با موفقیت ایجاد شد',
    updatedSuccess: 'نقش با موفقیت ذخیره شد',
    deletedSuccess: 'نقش حذف شد',
  },

  permissions: {
    title: 'سطوح دسترسی',
    subtitle: 'فهرست سطوح دسترسی سامانه. این فهرست را سرور می‌سازد و قابل ویرایش نیست.',

    readOnlyNote:
      'سطوح دسترسی از روی کنترلرهای سرور ساخته می‌شوند و مستقیما قابل تغییر نیستند. برای تعیین اینکه چه کسی به چه چیزی دسترسی دارد، آن‌ها را به یک نقش تخصیص دهید.',

    colTitle: 'شرح دسترسی',
    colName: 'شناسه',
    colGroup: 'بخش',

    filterTitle: 'جست‌وجو در شرح دسترسی',

    emptyTitle: 'سطح دسترسی یافت نشد',
    emptyBody: 'با فیلتر فعلی هیچ سطح دسترسی‌ای پیدا نشد.',

    /** Persian names for the resource prefix in a permission name (`User.Get` → `User`). */
    groups: {
      Bot: 'ربات‌های معاملاتی',
      BotHistory: 'سابقه ربات',
      Signal: 'سیگنال',
      KillSwitch: 'کلید توقف اضطراری',
      User: 'کاربران',
      Role: 'نقش‌ها',
      Permission: 'سطوح دسترسی',
      LoginHistory: 'تاریخچه ورود',
      Ml: 'موتور یادگیری ماشین',
    } as Record<string, string>,
  },

  loginHistory: {
    title: 'تاریخچه ورود',
    subtitle: 'تلاش‌های ورود به سامانه، به ترتیب زمان',

    // The endpoint is not scoped to the caller, so the page says whose attempts these are rather than
    // letting the reader assume they are their own.
    scopeNote: 'این فهرست تلاش‌های ورود همه کاربران سامانه را نشان می‌دهد.',

    colDateTime: 'زمان',
    colStatus: 'نتیجه',
    colIp: 'نشانی آی‌پی',
    colClient: 'دستگاه',

    filterIp: 'جست‌وجو در نشانی آی‌پی',

    statusSuccess: 'موفق',
    statusError: 'ناموفق',

    emptyTitle: 'تلاشی برای ورود ثبت نشده است',
    emptyBody: 'با فیلتر فعلی هیچ رکوردی پیدا نشد.',
  },

  notFound: {
    title: 'صفحه پیدا نشد',
    body: 'نشانی وارد شده وجود ندارد یا جابه‌جا شده است.',
    back: 'بازگشت به داشبورد',
  },

  errors: {
    network: 'ارتباط با سرور برقرار نشد. اتصال شبکه خود را بررسی کنید',
    unexpected: 'خطای پیش‌بینی نشده‌ای رخ داد',
    malformed: 'پاسخ سرور قابل پردازش نبود',
    forbidden: 'شما اجازه دسترسی به این بخش را ندارید',

    /**
     * Fallbacks by `ApiResultStatusCode`, used only when the API sends no message of its own. The
     * API's own Persian message is always preferred — it is more specific than anything generic
     * here, and it is what an operator would see in the logs.
     */
    byStatus: {
      200: 'عملیات با موفقیت انجام شد',
      204: 'محتوایی برای نمایش وجود ندارد',
      400: 'اطلاعات ارسال شده معتبر نیست',
      401: 'احراز هویت ناموفق بود',
      403: 'دسترسی شما به این بخش مجاز نیست',
      404: 'موردی یافت نشد',
      409: 'انجام این درخواست در وضعیت فعلی امکان‌پذیر نیست',
      422: 'اطلاعات ارسال شده قابل پردازش نیست',
      429: 'تعداد درخواست‌های شما بیش از حد مجاز است. کمی بعد دوباره تلاش کنید',
      500: 'خطایی در سرور رخ داده است',
      503: 'سرور در حال حاضر قادر به پاسخگویی نیست',
    } as Record<number, string>,
  },
} as const
