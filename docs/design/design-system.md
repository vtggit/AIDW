# Product family design system

One look and one way of working across the product family. The planner screen was the first
product built this way; this document is the shared standard every product's screens follow,
and the reference each product's port is checked against.

## Principles

These four principles answer the four failures of the earlier screens.

- **No endless pages.** The application is a fixed-height shell. On a desktop screen the page
  itself never scrolls: each screen fits the window, and only designated panes (a list, a table
  body, a detail pane) scroll on their own.
- **One plan, not pieces.** Every screen is built from the same handful of patterns below, with
  the same shell, header, spacing, type and status language, so the product reads as one thing.
- **Current, quiet visual language.** Tokens only (never raw colours or sizes), IBM Plex Sans for
  text and IBM Plex Mono for figures, tabular numbers, generous spacing, and one accent colour.
- **An obvious workflow.** Each screen answers one question, its primary action is a single
  primary button, and the user always sees where they are (an active nav item, the page title,
  the selected row).

## The application shell

- A fixed-height layout (`height: 100vh`, never taller) with two columns: a dark sidebar
  (`--sidebar-width`, 232 px) and the main area.
- **Sidebar**, top to bottom: the product mark and name, the navigation (one button per screen,
  the active one highlighted; counts where they help), and at the bottom the data status (for
  example "Synced today 07:30 UTC") and the signed-in user with Sign out.
- **Main area header**: the page title, a one-line subtitle, and on the right the as-of date or
  other context.
- Below the header, the screen fills the remaining height.
- Navigation is hash-based (`#/<screen>`), switches screens without a page load and survives a
  reload.

## Patterns

Every screen is one of these, or a combination of them on one page.

| Pattern | Use it for | Shape |
|---|---|---|
| **Overview** | What matters at a glance, for a manager | Value tiles in a row, then one card per area with its counts and a link into it, then a short "needs attention" list. Fits one screen. |
| **Work queue** | Working through items one at a time | Tabs, plus filter chips on one bar. A split pane: a list (about 60%, sticky header, scrolls on its own, a selected row tinted with a 3 px accent bar) and a detail pane (`--detail-width`, 440 px) with figures, a "Why" block and the actions. |
| **Table in a card** | Logs, registers, reference data | One card holding a table with a sticky header. The body scrolls inside the card. Row links go to the item's work view. |
| **Form in a pane** | Creating or editing one thing | A card or detail pane with labelled fields in one column, inline validation under each field, one primary button and a secondary Cancel. Never a page-long form: long forms become steps. |
| **Steps** | A guided multi-step task (a wizard) | A step list on the left and the current step's form on the right. Back and Next, with progress kept. |
| **Board or calendar** | Status lanes or dates | It fills the screen area, and lanes or days scroll inside their own region. |
| **Settings** | Configuration | Cards for System (admin) and Personal settings. Each row has its description, a control, where the value comes from, and "Reset to default". |

## Components and states

- **Buttons:** one primary (accent) per area, with secondary and quiet buttons around it. Real
  `<button>` elements, at least 44 px tall.
- **Status badges:** pills with these meanings: neutral grey for Undecided or Draft, pale accent
  for Accepted or Active, solid accent with white text for Applied or Done, grey for Dismissed,
  pale amber for Snoozed or Waiting, darker amber for Risk.
- **Empty state:** centred in its region, with a heading, one sentence saying what will appear
  here and how, and a link to where to start.
- **Loading:** skeleton rows in the real layout, never a bare "Loading…" line. Every render path
  ends in data, an empty state or an error.
- **Error:** inline in the region that failed, with the server's message and a Retry button.
  One region failing never blanks the whole screen.
- **Numbers:** whole units with thousands separators, money as whole dollars, one decimal for
  days and months, and a gap shown as a magnitude with a direction word ("1,465 units below").

## Tokens

The token file is `app/css/tokens.css`, and screens use its variables, never raw values.

- **Type:** IBM Plex Sans for UI text and IBM Plex Mono for figures, with tabular numbers
  throughout.
- **Colours:**
  - ground #EEF1F4; surface #FFFFFF; sidebar #16212C;
  - ink #17212B, secondary ink #4A5865;
  - borders #DDE3E9 and #E6EAEE;
  - accent #1D4ED8, for actions, the selection and "applied";
  - risk #8A3B05 on #FDE8D3.
- **Radii:** 8 px for controls, 12 px for cards, 999 px for pills.
- **Spacing:** 4 px steps (`--space-1` to `--space-7`); pages have 24–28 px padding.
- **Sizes:** touch targets at least 44 px, list rows at least 52 px.

## Narrow screens

At 900 px and below, the sidebar becomes a top bar, split panes stack, and every multi-column
grid becomes one column. That is the only time the page may scroll, and then only vertically.
Nothing may clip, overflow its box or scroll the page sideways.

## Accessibility

- Real `<button>`, `<a>`, `<input>` and `<label>` elements.
- Tabs use `role="tablist"`/`role="tab"` with `aria-selected`; toggle buttons use `aria-pressed`;
  switches use `role="switch"` with `aria-checked`; the selected row uses `aria-current`.
- Text contrast is at least 4.5:1, and colour is never the only signal.
- Every value that comes from an API is inserted as text, never as HTML.

## Configuration

Behaviour that reasonable teams could want differently has a default and a setting, never a
hard-coded choice. System settings need an admin, and Personal settings belong to each user.
Both are shown on the Settings screen.

## Proof of a screen

Each screen's browser proof checks:
- the screen's own behaviour;
- that the page does not scroll at 1440×900;
- that there is no sideways scroll at 390×844;
- that an injected `<img src=x onerror=…>` in API data renders as text.

## Porting an existing product

1. **Tokens and shell first.** Add the token file and the fonts, and wrap the existing screens in
   the shell (sidebar nav and header). Keep every existing element id, class and `data-*` hook
   that the product's tests use, so the move changes appearance and navigation, not behaviour.
2. **Then one screen per slice.** Map each screen to a pattern above and rebuild it to that
   pattern, keeping its test hooks or superseding the named proofs explicitly.
3. **Retire long pages last.** A screen that today is a long scrolling page becomes a pattern
   above (often a Work queue or a Table in a card plus a Form in a pane), not a shorter long page.
