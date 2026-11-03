# Design: GitHub Lens

The shared UI system for all workspace screens, login, mobile upload and overlays.

## System

- Genre: editorial, applied to app screens with practical information density.
- Theme: Specimen adapted to the user's warm paper and brown-orange direction.
- Keep the GitHub Lens name, existing destinations, forms, handlers and API behavior.
- The project archive and screenshot inbox carry the interface; no marketing hero.
- Screens share tokens and controls, and vary in composition according to their task.

## Tokens

`frontend/src/tokens.css` is the source of truth.

- Canvas: warm paper `--color-paper`; higher surface: `--color-paper-raised`.
- Sidebar and quiet wells: `--color-paper-2`; archive monograms: `--color-paper-3`.
- Text: `--color-ink`, `--color-ink-2`, `--color-muted`.
- Rules: `--color-rule`, `--color-rule-2`; fields: `--color-field-edge`.
- Accent: `--color-accent`, paired with `--color-accent-ink`; selected: `--color-accent-soft`.
- Focus, error and success have their own roles; status always includes text.
- Serif display uses locally available Georgia and Chinese serif fallbacks.
- Controls, navigation, data and body use Segoe UI / Microsoft YaHei.
- Monospace is restricted to code and raw source text.
- Shared spacing scale: 2, 4, 8, 12, 16, 24, 40, 64, 96 and 144px.

## Composition

- Existing desktop shell with a warm paper sidebar and a quiet header.
- Dashboard: screenshot workbench beside a ruled figures block, then archive entries.
- Projects: two-column archive entries with monograms, readable summaries and metadata.
- Detail: document column and a narrower facts / personal notes column.
- Imports and jobs: compact rows, clear status text and attached actions.
- Settings: labeled forms and service rows, without nested decorative panels.
- Below 960px the shell becomes a labeled navigation strip; all destinations remain available.
- Below 640px document columns and archive entries stack; actions wrap, never clip.

## Controls and motion

- Controls are 40px; small controls 36px with enlarged icon hit targets.
- One primary brown-orange button; secondary is a paper rectangle with a readable edge.
- Keyboard focus appears instantly; hover changes contrast, never moves a whole entry.
- No arrival choreography, paper texture, decorative status dots or invented metrics.
- Existing functional loading indicators stop under reduced motion.

## Exports

Tokens: `frontend/src/tokens.css`. Base: `frontend/src/base.css`.
Shared layout primitives: `styles.css`; research primitives: `research.css`.
Final screen composition: `archive.css`.

## Variants

- Project library: `project-library.css` uses bounded paper cards with stable repository-name tints, real GitHub owner avatars with a monogram fallback, visible study status and a stronger followed-project marker. The archive on the dashboard keeps its compact rows. Colors identify an item, without implying an inferred project category.
