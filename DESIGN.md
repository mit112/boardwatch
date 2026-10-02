---
name: boardwatch web
description: A calm, plain-spoken workspace for choosing, preparing and recording job applications, set on warm paper in dark ink with one forest green.
colors:
  forest: "#1d5a3c"
  forest-deep: "#154530"
  on-forest: "#fbf9f2"
  umber: "#7d4e00"
  brick: "#9a2a1c"
  lamplit-ivory: "#f6f1e6"
  paper: "#fcfaf4"
  parchment: "#efe8d8"
  worn-parchment: "#e6dcc7"
  deep-ink: "#1b2a22"
  ink-soft: "#3f4f46"
  ink-quiet: "#566559"
  control-edge: "#68776c"
  divider: "#e0d6c0"
typography:
  headline:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI Variable Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI Variable Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI Variable Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI Variable Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: "1.125rem"
    letterSpacing: "0"
rounded:
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  full: "9999px"
spacing:
  target: "2.75rem"
  header: "4.3125rem"
components:
  button-primary:
    backgroundColor: "{colors.forest}"
    textColor: "{colors.on-forest}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    height: "2.75rem"
    padding: "0 1.25rem"
  button-primary-hover:
    backgroundColor: "{colors.forest-deep}"
  button-quiet:
    backgroundColor: "{colors.parchment}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.sm}"
    height: "2.75rem"
    padding: "0 0.75rem"
  button-quiet-hover:
    backgroundColor: "{colors.worn-parchment}"
    textColor: "{colors.deep-ink}"
  lens-tab:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.sm}"
    height: "2.75rem"
    padding: "0 1rem"
  lens-tab-active:
    backgroundColor: "{colors.forest}"
    textColor: "{colors.on-forest}"
  field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.deep-ink}"
    rounded: "{rounded.sm}"
    height: "2.75rem"
    padding: "0 0.75rem"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.deep-ink}"
    rounded: "{rounded.md}"
    padding: "1rem"
  workspace:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.deep-ink}"
    rounded: "{rounded.lg}"
---

# Design System: boardwatch web

## Overview

**Creative North Star: "The Honest Ledger"**

The viewer is a careful record kept for one person's job search. Everything on it is set on warm paper in dark ink, with a single forest green that means "this is the thing to do" or "this was confirmed". A reading is shown as it was read: satisfied, unmet, unconfirmed or not assessed, each with a glyph and a sentence, never a colour alone and never a combined score. It is a working surface for a daily sitting, so it favours scanning, large targets and quiet: one filled button per view, sentence-case labels, no decoration that does not carry state.

Density is moderate and list-first. A page opens on the job list with a short summary above it, and a job opens into a workspace beside the list on wide screens or as a full-screen sheet on narrow ones. The tone is plain-spoken: the interface says what happened in the past tense ("Application recorded for Acme."), and says "Check" where it does not know.

Confirmed anti-references: gamified progress (streaks, badges, confetti, score rings, countdowns), walls of equal-weight counters with bordered chips, and traffic-light verdicts where colour alone carries meaning.

**Key Characteristics:**
- Warm ivory paper, deep green-black ink, one forest accent; two themes, light by default, following the system with an explicit toggle.
- Meaning is always glyph + words + colour, in that order of reliability.
- 44px targets, a visible 2px focus ring everywhere, and no control ever hidden under sticky chrome.
- Tonal layering with one soft ambient shadow; no hard blocks, no coloured glows.
- One system sans, no bundled font; monospace only for paths, rule names and quoted source text.

## Colors

A warm, low-chroma paper-and-ink palette with a single deep forest green. Contrast is computed against the worst surface a token is ever painted on, never against the page.

### Primary
- **Forest** (#1d5a3c): the one filled action per view, links, the selected mark, focus rings, and "confirmed satisfied". Its dark-theme counterpart is lifted to stay above 4.5:1.
- **Deep Forest** (#154530): the pressed and hover fill of the primary action.
- **Pressed Paper** (#fbf9f2): text on a forest fill (7.73:1).

### Secondary
- **Umber** (#7d4e00): "not confirmed, something to check". Always beside a question-mark glyph and a sentence.

### Tertiary
- **Brick** (#9a2a1c): "confirmed unmet" or "closed". Always beside a cross glyph and a sentence.

### Neutral
- **Lamplit Ivory** (#f6f1e6): the page.
- **Paper** (#fcfaf4): the working surface: list, workspace, cards, fields.
- **Parchment** (#efe8d8): panels and quiet controls that sit on paper.
- **Worn Parchment** (#e6dcc7): hover and the open row; the strongest fill a token lands on.
- **Deep Ink** (#1b2a22): primary text (11:1).
- **Soft Ink** (#3f4f46): secondary text (6.4:1).
- **Quiet Ink** (#566559): tertiary text and placeholders; the floor of the text scale (4.54:1).
- **Control Edge** (#68776c): a control's border; clears 3:1 on every surface.
- **Faded Rule** (#e0d6c0): dividers only; decorative, never carries meaning.

**Dark theme.** Same hierarchy on warm near-black, not blue-black: page #14130f, paper #1b1a15, parchment #24231c, worn parchment #2f2d24, ink #f2ede0, soft ink #c3bcaa, quiet ink #a49d8a, accent #86cfa3, primary fill #6dbd8b, umber #e7b95c, brick #f09a8c. The tokens carry the same names; only the values change.

### Named Rules
**The Three Channels Rule.** A status is a glyph, a sentence and a colour. Remove the colour and it still reads; remove the glyph and the sentence still says it.
**The One Forest Rule.** The forest fill appears once per view as the primary action. Forest as text (links, "confirmed") is allowed; a second filled green button is not.
**The Worst Surface Rule.** A text colour is checked against the darkest surface it is painted on. A ratio recorded against the page is a guard in the wrong scope.

## Typography

**Display Font:** the platform UI sans (ui-sans-serif, system-ui, -apple-system, Segoe UI Variable Text, Roboto, Helvetica Neue, Arial)
**Body Font:** the same stack; nothing is downloaded or bundled
**Label/Mono Font:** the same sans for labels; ui-monospace (SF Mono, Menlo, Consolas) only for file paths, rule names and quoted source

**Character:** one voice. Weight and size carry the hierarchy, tracking stays near neutral, and nothing is set in capitals.

### Hierarchy
- **Headline** (600, 1.25rem, 1.25): a panel or confirmation heading ("Application recorded for Acme.").
- **Title** (600, 1.125rem, 1.25): the workspace job title and section titles.
- **Body** (400, 0.9375rem, 1.5): list rows, descriptions and prose, held to about 56–72ch where it is a paragraph.
- **Label** (500, 0.8125rem, 1.125rem, no tracking, sentence case): names a value beside it.
- **Figure** (600, 1.5rem, tabular numerals): the few headline numbers in the summary strip; every number is tabular.

### Named Rules
**The No-Shouting Rule.** No uppercase micro-labels and no wide tracking. A label names the thing beside it and needs neither.
**The One Sans Rule.** A task tool needs no display face. A new font is a download, a licence and a layout shift for no gain in the task.

## Layout

A list-first, two-column workspace. At and above 1024px the job list and the workspace sit side by side and the workspace keeps its place; below 1024px a job opens as a full-screen modal sheet over an inert page. Content sits in a page gutter of 16px below 640px and 24px from 640px up, in a column no wider than 160rem. Spacing follows the platform's 4px rhythm; panels use 16px padding, the summary strip 16px with 32px between columns.

Targets are at least 44px high; a checkbox is allowed to be smaller only where nothing sits inside its 24px circle. The app header sticks only where there is room for it (at least 42rem wide and 34rem tall, where it is one row, 4.3125rem); below that it scrolls away, so a focused control cannot be covered at 200% zoom or on a phone. Sticky bars reserve their height with `scroll-margin` (7.5rem above, 6rem below). Reflow holds at 320px with no two-dimensional scrolling; wide tables scroll inside their own container.

### Named Rules
**The Never-Obscured Rule.** Whatever is sticky must be accounted for in `scroll-margin`, and anything that would cover a quarter of the screen does not stick.

## Elevation & Depth

Tonal layering first, one soft shadow second. Depth is conveyed by moving up the surface scale (page, paper, parchment, worn parchment); the single shadow token lifts a card or the workspace off the page.

### Shadow Vocabulary
- **Card** (`box-shadow: 0 1px 2px var(--shadow-ink), 0 14px 32px -22px var(--shadow-ink)`): the summary strip, the workspace and unselected lens tabs. `--shadow-ink` is a warm brown at 16% on light and black at 55% on dark.

### Named Rules
**The Ink Shadow Rule.** A shadow is soft, offset and in the page's own ink, never a hard block and never a coloured halo.

## Shapes

A three-step radius language and nothing else: 0.5rem for controls, 0.75rem for panels, 1rem for the workspace, and a full circle only for the recorded-check disc. The bare `rounded` utility does not exist, so a corner is always chosen. Rows are separated by space and a faded rule, not by boxes; one sentence per row replaced a row of up to six bordered chips.

## Components

Every control is calm, plain and large.

### Buttons
- **Shape:** gently curved (0.5rem), 44px high.
- **Primary:** Forest fill, Pressed Paper text, 600 weight, 20px side padding, with an arrow icon where it moves forward. One per view.
- **Hover / Focus:** the fill deepens to Deep Forest over 150ms; focus is the global 2px forest ring with a 2px offset.
- **Quiet:** text-only or Parchment fill, Soft Ink text, 12px side padding; hover goes to Worn Parchment and Deep Ink. Used for Undo, Back, End session and every secondary action.
- **Disabled:** Worn Parchment fill and Quiet Ink text; the control stays in the tab order only where it is meaningful.

### Navigation
- **Style:** text tabs in a row, 44px high. The active tab is Parchment with a 2px forest underline drawn inset and 600 weight; inactive tabs are Soft Ink and brighten on hover. A theme toggle sits at the end.
- **Lens tabs** (Jobs to explore, Needs review, All jobs) are a group of `aria-pressed` buttons: the active one is a Forest fill, the others Paper with the card shadow. Each carries its count as part of its name.

### Inputs / Fields
- **Style:** Paper fill, 1px Control Edge border, 0.5rem radius, 44px high, 12px padding, Quiet Ink placeholder.
- **Focus:** the border moves to Soft Ink and the global focus ring appears.
- **Error / Disabled:** errors are stated in a sentence beside the field, never by colour alone.

### Cards / Containers
- **Corner Style:** 0.75rem for panels and the summary strip; 1rem for the workspace.
- **Background:** Paper on the Ivory page; Parchment for a panel inside a card.
- **Shadow Strategy:** the single Card shadow (see Elevation).
- **Internal Padding:** 16px, 24px for the workspace and recorded panel.

### Status Mark
One reading as a glyph and a sentence in plain text, not a badge: a tick for confirmed satisfied, a question mark for "check", a cross for confirmed unmet or closed, a dash for not assessed or pending. The tone colour is Forest, Umber, Brick or Quiet Ink; the glyph shape and the words carry it without the colour.

### Summary Strip (signature component)
A short line of what matters: what is new, applications recorded today and in the past 7 days, what needs attention, and one primary "Start applying" action. A zero is printed as a zero, and when a search narrows the counts the labels say "in this search". It replaced sixteen pipeline counters, which now sit one click away.

### Apply Session and Recorded Panel
A quiet strip above the list ("Apply session, 2 recorded this session") and, after a record, a panel that says "Recording your application for Acme…" with a neutral dash until the server answers, then "Application recorded for Acme." with a tick, Continue, Undo and Back. No goal, no streak, no countdown.

## Do's and Don'ts

### Do:
- **Do** pair every colour meaning with a glyph and a sentence; check text contrast against the worst surface it sits on (4.5:1 text, 3:1 control edges).
- **Do** keep one filled forest button per view and make everything else quiet.
- **Do** use tabular numerals for every figure and print a zero as a zero.
- **Do** keep targets at 44px, the 2px forest focus ring visible on everything, and sticky chrome out of the way of focus (`scroll-margin`, and no sticky header below 42rem or 34rem tall).
- **Do** say what happened in the past tense, and say "Check" where the tool does not know.
- **Do** use the three radii (0.5, 0.75, 1rem) and the one Card shadow; resolve every colour, radius and easing curve through a token.

### Don't:
- **Don't** use streaks, badges, confetti, score rings, progress goals or countdowns; progress is the person's own recorded effort and nothing pushes it.
- **Don't** build a wall of equal-weight counters or a row of bordered chips; one sentence per row.
- **Don't** let colour alone carry a verdict, and don't fold the four readings into one red/amber/green fit badge.
- **Don't** set uppercase micro-labels, add wide tracking, or bundle a web font.
- **Don't** use a hard-edged or coloured shadow, a gradient, a springy easing, or a second filled green button in the same view.
- **Don't** hard-code a hex, a pixel radius or a cubic-bezier; the default palette, radius scale and easing are cleared so the promise is structural.
