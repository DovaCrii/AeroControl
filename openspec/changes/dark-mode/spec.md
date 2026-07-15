# Spec — Dark Mode Toggle

## Functional Requirements

### F1: CSS Variables
- All color references use CSS custom properties
- `[data-theme="dark"]` selector overrides for:
  - Background (body, sidebar, cards, navbar)
  - Text colors (primary, muted, headings)
  - Border and shadow colors
  - Table hover and sidebar active states
  - Form controls (input bg, border, focus ring)

### F2: Toggle Button
- Sun/moon icon button in the top navbar
- Accessible: aria-label, role="button"

### F3: Persistence
- On toggle: save `theme` key in localStorage
- On page load: read localStorage → if not set, check `prefers-color-scheme`
- Set `data-theme` attribute on `<html>` element

### F4: HTMX Compatibility
- Theme persists across HTMX partial swaps (data-theme on html is outside swap targets)
