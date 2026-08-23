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
  },

  nav: {
    overview: 'نمای کلی',
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
  },

  placeholder: {
    title: 'این بخش هنوز ساخته نشده است',
    body: 'زیرساخت احراز هویت و چیدمان داشبورد آماده است. این صفحه در گام‌های بعدی تکمیل می‌شود.',
  },

  /** Shared table chrome: the pager, the filter bar, and the states a listing can be in. */
  table: {
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
