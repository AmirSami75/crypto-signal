import { useId } from 'react'

/**
 * A dependency-free mini bar chart, horizontal or vertical.
 *
 * Same doctrine as Charts.tsx: no charting library (its layout engine and colour opinions would
 * have to be fought in RTL), theme tokens for fills, and `dir="ltr"` on the SVG itself — a data
 * axis reads in data order regardless of script direction. Negative values grow from a zero
 * baseline in the danger tone; non-negative values use the accent tone unless `tone` overrides.
 */

type BarTone = 'accent' | 'success' | 'danger'

const FILLS: Record<BarTone, string> = {
  accent: 'var(--brand)',
  success: 'var(--success)',
  danger: 'var(--danger)',
}

export function BarSeries({
  values,
  orientation = 'horizontal',
  tone,
  height = 72,
  ariaLabel,
  className = '',
}: {
  values: number[]
  orientation?: 'horizontal' | 'vertical'
  tone?: BarTone
  height?: number
  ariaLabel: string
  className?: string
}) {
  const id = useId()
  if (values.length === 0) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-dashed border-line text-xs text-ink-faint ${className}`}
        style={{ height }}
      >
        —
      </div>
    )
  }

  const max = Math.max(0, ...values)
  const min = Math.min(0, ...values)
  const span = max - min || 1

  if (orientation === 'horizontal') {
    const rowH = Math.max(14, Math.min(26, Math.floor((height - 8) / values.length)))
    const h = rowH * values.length + 8
    return (
      <svg
        role="img"
        aria-label={`${ariaLabel} (${id})`}
        viewBox={`0 0 300 ${h}`}
        preserveAspectRatio="none"
        className={className}
        style={{ height: h, direction: "ltr" }}
      >
        {values.map((v, i) => {
          const zeroX = 8 + ((-min / span) * 284)
          const w = Math.max(2, (Math.abs(v) / span) * 284)
          const x = v >= 0 ? zeroX : zeroX - w
          const fill = tone ? FILLS[tone] : v >= 0 ? 'var(--brand)' : 'var(--danger)'
          return (
            <rect
              key={i}
              x={x.toFixed(2)}
              y={(4 + i * rowH).toFixed(2)}
              width={w.toFixed(2)}
              height={rowH - 5}
              rx={2}
              fill={fill}
              opacity={0.85}
            />
          )
        })}
      </svg>
    )
  }

  const W = 300
  const zeroY = 4 + ((max / span) * (height - 8))
  const slot = (W - 8) / values.length
  const bw = Math.max(3, slot - 3)
  return (
    <svg
      role="img"
      aria-label={`${ariaLabel} (${id})`}
      viewBox={`0 0 ${W} ${height}`}
      preserveAspectRatio="none"
      className={className}
      style={{ height, direction: 'ltr' }}
    >
      {values.map((v, i) => {
        const h = Math.max(2, (Math.abs(v) / span) * (height - 8))
        const y = v >= 0 ? zeroY - h : zeroY
        const fill = tone ? FILLS[tone] : v >= 0 ? 'var(--brand)' : 'var(--danger)'
        return (
          <rect
            key={i}
            x={(4 + i * slot + (slot - bw) / 2).toFixed(2)}
            y={y.toFixed(2)}
            width={bw.toFixed(2)}
            height={h.toFixed(2)}
            rx={1.5}
            fill={fill}
            opacity={0.85}
          />
        )
      })}
    </svg>
  )
}
