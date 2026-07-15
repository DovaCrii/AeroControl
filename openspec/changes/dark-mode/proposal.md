# Dark Mode Toggle

## Problem
The app only has a light theme. For desktop use in dim environments or at night, dark mode reduces eye strain.

## Proposed Scope
1. CSS custom properties overrides for dark theme
2. Toggle button in navbar (sun/moon icon)
3. Persist preference in localStorage
4. Respect system prefers-color-scheme as default
5. Smooth transition between themes

## Non-goals
- Multiple theme variants (just light/dark)
- Per-page theme customization
