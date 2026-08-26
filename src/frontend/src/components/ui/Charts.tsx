/**
 * Inline SVG charts.
 *
 * Deliberately dependency-free. A charting library would bring its own layout engine, its own
 * colour system, and its own opinions about direction — and this dashboard is RTL with a themed
 * token palette, so all three would have to be fought. These draw a few hundred bytes of SVG,
 * inherit `currentColor` and the theme variables, and lay out left-to-right *as charts should*
 * even inside an RTL document: a time axis reads oldest-to-newest by convention regardless of
 * script direction, which is why every chart here sets `dir="ltr"` on its own SVG.
 */

type Point = { x: number; y: number }

/** Maps data points into an SVG viewBox, padding a flat series so it does not collapse to a line. */
function project(values: number[], width: number, height: number, pad = 4): Point[] {
  if (values.length === 0) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  // A constant series has zero range; centre it rather than dividing by zero.
  const span = max - min || Math.abs(max) || 1
  const usableHeight = height - pad * 2
  const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0

  return values.map((value, index) => ({
    x: pad + index * step,
    y: pad + usableHeight - ((value - min) / span) * usableHeight,
  }))
}

function toPath(points: Point[]): string {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ')
}

export type LineChartProps = {
  values: number[]
  /** Optional horizontal reference line in data units — e.g. a confidence floor or break-even. */
  threshold?: number
  /** Colour the fill and stroke by sign: green above zero, red below. For P&L curves. */
  signed?: boolean
  height?: number
  ariaLabel: string
}

/**
 * A filled line chart sized to its container.
 *
 * `preserveAspectRatio="none"` lets one viewBox stretch to any card width — the shape of the
 * series is what carries meaning here, not its aspect ratio.
 */
export function LineChart({ values, threshold, signed = false, height = 64, ariaLabel }: LineChartProps) {
  const WIDTH = 300
  const points = project(values, WIDTH, height)

  if (points.length === 0)
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-line text-xs text-ink-faint"
        style={{ height }}
      >
        —
      </div>
    )

  const last = values[values.length - 1] ?? 0
  const tone = signed ? (last >= 0 ? 'var(--success)' : 'var(--danger)') : 'var(--brand)'
  const path = toPath(points)
  const area = `${path} L${points[points.length - 1].x.toFixed(2)},${height} L${points[0].x.toFixed(2)},${height} Z`

  // The threshold shares the series' scale, so it has to be projected through the same mapping.
  let thresholdY: number | null = null
  if (threshold !== undefined) {
    const min = Math.min(...values, threshold)
    const max = Math.max(...values, threshold)
    const span = max - min || 1
    thresholdY = 4 + (height - 8) - ((threshold - min) / span) * (height - 8)
  }

  const gradientId = `grad-${ariaLabel.replace(/\W/g, '')}`

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      preserveAspectRatio="none"
      className="w-full"
      style={{ height, direction: 'ltr' }}
      role="img"
      aria-label={ariaLabel}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={tone} stopOpacity="0.28" />
          <stop offset="100%" stopColor={tone} stopOpacity="0" />
        </linearGradient>
      </defs>

      {thresholdY !== null && (
        <line
          x1="0"
          y1={thresholdY}
          x2={WIDTH}
          y2={thresholdY}
          stroke="var(--ink-faint)"
          strokeWidth="1"
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />
      )}

      <path d={area} fill={`url(#${gradientId})`} />
      <path
        d={path}
        fill="none"
        stroke={tone}
        strokeWidth="1.75"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="2.5" fill={tone} />
    </svg>
  )
}

export type BarChartProps = {
  /** Each bar's height fraction in [0,1]; null renders an empty slot so gaps stay visible. */
  values: (number | null)[]
  labels: string[]
  /** Optional per-bar emphasis, e.g. the bucket a live confidence currently sits in. */
  highlightIndex?: number
  ariaLabel: string
}

/**
 * A labelled bar chart for calibration buckets.
 *
 * Bars are CSS rather than SVG: they carry text labels underneath and need to reflow at 375px,
 * which flex handles and a fixed viewBox does not.
 */
export function BarChart({ values, labels, highlightIndex, ariaLabel }: BarChartProps) {
  return (
    <div className="flex items-end gap-1.5" style={{ height: 96 }} role="img" aria-label={ariaLabel}>
      {values.map((value, index) => {
        const empty = value === null
        const share = empty ? 0 : Math.max(0.02, Math.min(1, value))
        return (
          <div key={labels[index]} className="flex min-w-0 flex-1 flex-col items-center gap-1">
            <div className="flex w-full flex-1 items-end">
              <div
                className={`w-full rounded-t transition-[height] ${
                  empty
                    ? 'bg-line'
                    : index === highlightIndex
                      ? 'bg-accent'
                      : 'bg-accent/45'
                }`}
                style={{ height: `${share * 100}%` }}
                title={empty ? '—' : `${(share * 100).toFixed(0)}%`}
              />
            </div>
            <span className="num truncate text-[0.625rem] text-ink-faint" dir="ltr">
              {labels[index]}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export type CandleChartProps = {
  candles: { openTime: string; open: number; high: number; low: number; close: number }[]
  height?: number
  ariaLabel: string
}

/**
 * Price chart: a close line over a translucent high-low band.
 *
 * Real candlesticks need one-pixel-per-candle widths that fall apart at 375px, and a close line
 * with a wick band carries the same information at every width. Green/red follows the window's
 * overall direction — up if the last close beats the first open.
 */
export function CandleChart({ candles, height = 120, ariaLabel }: CandleChartProps) {
  const WIDTH = 300
  const closes = candles.map(c => c.close)
  const lows = candles.map(c => c.low)
  const highs = candles.map(c => c.high)

  if (closes.length < 2)
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-line text-xs text-ink-faint"
        style={{ height }}
      >
        —
      </div>
    )

  const min = Math.min(...lows)
  const max = Math.max(...highs)
  const span = max - min || Math.abs(max) || 1
  const pad = 4
  const usable = height - pad * 2
  const step = (WIDTH - pad * 2) / (candles.length - 1)
  const yOf = (v: number) => pad + usable - ((v - min) / span) * usable

  // Band polygon walks highs left-to-right then lows right-to-left.
  const band =
    highs.map((h, i) => `${i === 0 ? 'M' : 'L'}${(pad + i * step).toFixed(2)},${yOf(h).toFixed(2)}`).join(' ') +
    ' ' +
    lows
      .map((l, i) => `L${(pad + i * step).toFixed(2)},${yOf(l).toFixed(2)}`)
      .reverse()
      .join(' ')
      .replace(/^L/, 'L') + // keep explicit L commands for the reverse walk
    ' Z'
  const closePath = closes
    .map((c, i) => `${i === 0 ? 'M' : 'L'}${(pad + i * step).toFixed(2)},${yOf(c).toFixed(2)}`)
    .join(' ')

  const rising = closes[closes.length - 1] >= candles[0].open
  const tone = rising ? 'var(--success)' : 'var(--danger)'
  const gradientId = `candle-${ariaLabel.replace(/\W/g, '')}`

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      preserveAspectRatio="none"
      className="w-full"
      style={{ height, direction: 'ltr' }}
      role="img"
      aria-label={ariaLabel}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={tone} stopOpacity="0.18" />
          <stop offset="100%" stopColor={tone} stopOpacity="0.04" />
        </linearGradient>
      </defs>
      <path d={band} fill={`url(#${gradientId})`} stroke="none" />
      <path d={closePath} fill="none" stroke={tone} strokeWidth="1.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  )
}
