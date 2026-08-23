#!/usr/bin/env node
// @ts-check
/**
 * Mechanical RTL gate.
 *
 * The dashboard's mirroring comes from one thing — `dir="rtl"` on <html> — and holds only as long as
 * layout is written with **logical** properties. One `pl-4` looks right on the day it is written and is
 * wrong the moment the document flips: padding that should hug the text hugs the left edge instead.
 * That class of bug is invisible in review and obvious to a Persian reader, so it is checked by a
 * script rather than by discipline.
 *
 * The check is deliberately dumb — a substring scan over source text, not a CSS parser. It cannot know
 * whether a given `left-0` is genuinely wrong, so it treats every physical-direction utility as a
 * finding and requires an explicit `rtl-audit-ignore` on the line to allow one. Being told to justify
 * the exception is the point.
 *
 * Comments are blanked before scanning (character-for-character, so line and column numbers survive),
 * because prose that *names* a forbidden utility in order to explain why it is forbidden is not itself
 * a violation.
 *
 * Run: `npm run rtl:audit`
 */

import { readdir, readFile } from 'node:fs/promises'
import { join, relative, extname } from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND_ROOT = fileURLToPath(new URL('..', import.meta.url))
const SCAN = ['src', 'index.html']
const EXTENSIONS = new Set(['.ts', '.tsx', '.css', '.html'])
const IGNORE_MARKER = 'rtl-audit-ignore'

/**
 * Tailwind utilities whose CSS resolves to a physical side, each with the logical utility to use
 * instead. Extend the list rather than adding an ignore comment when something new turns up.
 */
const CLASS_RULES = [
  { names: ['pl'], use: 'ps-*' },
  { names: ['pr'], use: 'pe-*' },
  { names: ['ml'], use: 'ms-*' },
  { names: ['mr'], use: 'me-*' },
  { names: ['scroll-pl'], use: 'scroll-ps-*' },
  { names: ['scroll-pr'], use: 'scroll-pe-*' },
  { names: ['scroll-ml'], use: 'scroll-ms-*' },
  { names: ['scroll-mr'], use: 'scroll-me-*' },
  { names: ['left'], use: 'start-*' },
  { names: ['right'], use: 'end-*' },
  { names: ['border-l', 'border-r'], use: 'border-s-* / border-e-*' },
  { names: ['rounded-l', 'rounded-r'], use: 'rounded-s-* / rounded-e-*' },
  { names: ['rounded-tl', 'rounded-tr', 'rounded-bl', 'rounded-br'], use: 'rounded-ss-* … rounded-ee-*' },
  { names: ['text-left', 'text-right'], use: 'text-start / text-end' },
  { names: ['float-left', 'float-right'], use: 'float-start / float-end' },
  { names: ['clear-left', 'clear-right'], use: 'clear-start / clear-end' },
  { names: ['object-left', 'object-right'], use: 'a logical position, or an rtl-audit-ignore' },
  { names: ['bg-left', 'bg-right'], use: 'a logical position, or an rtl-audit-ignore' },
  { names: ['origin-left', 'origin-right'], use: 'origin-center, or an rtl-audit-ignore' },
]

/** Raw CSS properties, for `styles.css` and any inline <style>. */
const CSS_RULES = [
  { pattern: /padding-(left|right)\s*:/g, use: 'padding-inline-start / padding-inline-end' },
  { pattern: /margin-(left|right)\s*:/g, use: 'margin-inline-start / margin-inline-end' },
  { pattern: /border-(left|right)(-\w+)?\s*:/g, use: 'border-inline-start / border-inline-end' },
  { pattern: /(?<![\w-])(left|right)\s*:/g, use: 'inset-inline-start / inset-inline-end' },
  { pattern: /text-align\s*:\s*(left|right)/g, use: 'text-align: start / end' },
  { pattern: /float\s*:\s*(left|right)/g, use: 'float: inline-start / inline-end' },
]

const findings = []
let scannedFiles = 0

/** Blanks comments while preserving every line break and offset, so positions stay accurate. */
function blankComments(source) {
  const blank = (match) => match.replace(/[^\n]/g, ' ')
  return source
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    // Line comments only when `//` is not part of a URL — `https://` must survive.
    .replace(/(^|[^:\w])\/\/[^\n]*/g, (match, lead) => lead + blank(match.slice(lead.length)))
}

function classPattern(name) {
  // Leading `-` allows the negative form (`-ml-2`); the lookbehind stops the name from matching inside
  // a longer token such as `--line-strong`.
  //
  // The tail is the fiddly part. `pl` is only ever a violation with a value (`pl-4`), so it demands the
  // hyphen. A side-suffixed name is a violation both bare and valued — `border-r` and `border-r-2`,
  // `rounded-tl-xl` — so it accepts a hyphen *or* a token boundary. Requiring the boundary alone was
  // the first version of this line and it silently passed `border-r-2`; accepting the hyphen alone
  // would pass a bare `border-r`. What the boundary must still exclude is a longer word that merely
  // starts the same way: `border-line` and `rounded-lg` are not `border-l` and `rounded-l`.
  const tail = /^[a-z-]+-(left|right|l|r|tl|tr|bl|br)$/.test(name) ? '(?=-|[^\\w-]|$)' : '-'
  return new RegExp(`(?<![A-Za-z0-9_])-?${name.replace(/[-]/g, '\\-')}${tail}`, 'g')
}

const COMPILED = CLASS_RULES.flatMap((rule) =>
  rule.names.map((name) => ({ name, use: rule.use, pattern: classPattern(name) })),
)

async function* walk(entry) {
  const absolute = join(FRONTEND_ROOT, entry)
  let children
  try {
    children = await readdir(absolute, { withFileTypes: true })
  } catch {
    // Not a directory — a single file target such as index.html.
    yield absolute
    return
  }
  for (const child of children) {
    const next = join(entry, child.name)
    if (child.isDirectory()) yield* walk(next)
    else if (EXTENSIONS.has(extname(child.name))) yield join(FRONTEND_ROOT, next)
  }
}

for (const target of SCAN) {
  for await (const file of walk(target)) {
    if (!EXTENSIONS.has(extname(file))) continue

    const source = await readFile(file, 'utf8')
    const rawLines = source.split('\n')
    const lines = blankComments(source).split('\n')
    const isCss = extname(file) === '.css'
    scannedFiles++

    lines.forEach((line, index) => {
      if (rawLines[index].includes(IGNORE_MARKER)) return

      for (const rule of isCss ? [] : COMPILED) {
        for (const match of line.matchAll(rule.pattern))
          findings.push({ file, line: index + 1, found: match[0].trim(), use: rule.use })
      }

      for (const rule of isCss ? CSS_RULES : [])
        for (const match of line.matchAll(rule.pattern))
          findings.push({ file, line: index + 1, found: match[0].trim(), use: rule.use })
    })
  }
}

// A positive check to go with the negative ones: every logical utility above resolves against the
// document direction, so the direction itself is the single point of failure for the whole design.
const html = await readFile(join(FRONTEND_ROOT, 'index.html'), 'utf8')
if (!/<html[^>]*\bdir="rtl"/.test(html))
  findings.push({ file: join(FRONTEND_ROOT, 'index.html'), line: 1, found: '<html> without dir="rtl"', use: 'dir="rtl" on <html>' })
if (!/<html[^>]*\blang="fa"/.test(html))
  findings.push({ file: join(FRONTEND_ROOT, 'index.html'), line: 1, found: '<html> without lang="fa"', use: 'lang="fa" on <html>' })

if (findings.length === 0) {
  console.log(`rtl-audit: ${scannedFiles} files, no physical-direction properties.`)
  process.exit(0)
}

console.error(`rtl-audit: ${findings.length} finding(s) in ${scannedFiles} files scanned.\n`)
for (const finding of findings)
  console.error(`  ${relative(FRONTEND_ROOT, finding.file)}:${finding.line}  ${finding.found}  →  use ${finding.use}`)
console.error(
  `\nLogical properties flip with dir="rtl"; physical ones do not. If one is genuinely correct — a` +
    ` handed glyph, say — put "${IGNORE_MARKER}" on the line with a reason.`,
)
process.exit(1)
