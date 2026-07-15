# Design — Dark Mode Toggle

## Architecture

### CSS Strategy
- `:root` has all light colors (existing)
- `[data-theme="dark"]` overrides specific variables
- Inline `<style>` in base.html head for flash-free load (before render)

### Toggle Script
```javascript
// Inline in base.html <head>
(function() {
  const stored = localStorage.getItem('theme');
  const preferred = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', stored || preferred);
})();
```

### Toggle Handler
```javascript
function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
}
```

### Files Modified
| File | Change |
|------|--------|
| `static/css/app.css` | Add `[data-theme="dark"]` variable overrides |
| `templates/base.html` | Add inline script, toggle button, dark CSS |

### Dark Theme Colors
| Variable | Light | Dark |
|----------|-------|------|
| Body bg | #F8F9FA | #0f1419 |
| Card/sidebar bg | #fff | #1a1f2e |
| Navbar bg | #1B2A4A | #0d1520 |
| Text primary | #243247 | #e1e7ef |
| Text muted | #6c757d | #8892a4 |
| Border/shadow | rgba(0,0,0,0.06) | rgba(255,255,255,0.06) |
| Table hover | #f0faf9 | #1a2a35 |
| Input bg | #fff | #1a1f2e |
| Input border | #dee2e6 | #2a3040 |
