# Design System Strategy: The Academic Atelier

## 1. Overview & Creative North Star
This design system moves away from the "industrial" feel of standard learning management systems and toward the **"Academic Atelier."** Our North Star is the concept of **Architectural Clarity**: a space that feels as structured and authoritative as a university library, yet as fluid and modern as a high-end research lab. 

We break the "template" look by rejecting the standard 1px grid. Instead, we use **Intentional Asymmetry** and **Tonal Depth** to guide the eye. By leveraging a high-contrast typography scale (Manrope for headers, Inter for data), we create an editorial feel where information isn't just displayed—it is curated. The layout should breathe, using generous whitespace (`spacing.12` to `spacing.20`) to separate high-level departmental functions from granular data.

## 2. Colors & Surface Logic
The palette is rooted in a deep, scholarly `primary` (#002045) and a sophisticated range of architectural greys. 

### The "No-Line" Rule
To achieve a premium, editorial feel, **designers are prohibited from using 1px solid borders for sectioning.** Physical boundaries must be defined solely through background color shifts.
*   **Context:** A `surface-container-low` (#f1f4f6) sidebar sitting against a `surface` (#f7fafc) main content area creates a natural, sophisticated break without the "boxed-in" feeling of a line.

### Surface Hierarchy & Nesting
Treat the dashboard as a series of nested physical layers. 
*   **Level 0 (The Foundation):** Use `surface` (#f7fafc) for the global backdrop.
*   **Level 1 (The Content Block):** Use `surface-container-lowest` (#ffffff) for primary workspaces or data cards.
*   **Level 2 (The Interactive Layer):** Use `surface-container-high` (#e5e9eb) for hover states or active selection indicators.

### The "Glass & Signature" Rule
*   **Glassmorphism:** For floating modals or "quick-view" academic profiles, use a semi-transparent `surface-container-lowest` with a `backdrop-blur` of 12px.
*   **Signature Textures:** Apply a subtle linear gradient from `primary` (#002045) to `primary-container` (#1a365d) on primary CTAs (e.g., "Submit Research") to provide a "silk-finish" depth that flat colors lack.

## 3. Typography
We utilize a dual-typeface system to balance institutional authority with modern readability.

*   **Display & Headlines (Manrope):** Chosen for its geometric precision. Use `display-lg` (3.5rem) for departmental titles and `headline-sm` (1.5rem) for section headers. The wide tracking of Manrope provides an "open" academic feel.
*   **Body & Labels (Inter):** The workhorse for data-heavy views. Use `body-md` (0.875rem) for student lists and `label-md` (0.75rem) for status indicators. 
*   **Editorial Contrast:** Always pair a `headline-lg` in `on-surface` (#181c1e) with a `body-sm` in `on-surface-variant` (#43474e) to create a clear hierarchy of importance.

## 4. Elevation & Depth
In the Academic Atelier, hierarchy is felt through "Tonal Layering" rather than heavy drop shadows.

*   **The Layering Principle:** To lift a component, don't add a shadow; shift the token. A card using `surface-container-lowest` sitting on a `surface-container-low` background creates a "soft lift."
*   **Ambient Shadows:** If a floating element (like a Rich Text Editor toolbar) requires a shadow, it must be an "Ambient Glow": `y-offset: 4px, blur: 24px, color: on-surface (opacity 4%)`.
*   **The Ghost Border Fallback:** If a border is required for accessibility (e.g., input fields), use the `outline-variant` (#c4c6cf) at **20% opacity**. Never use 100% opaque borders.

## 5. Components

### Buttons
*   **Primary:** Gradient fill (`primary` to `primary-container`), white text, `rounded-md` (0.375rem). Use for high-intent actions like "Publish Grades."
*   **Outlined:** A "Ghost Border" of `outline` (#74777f) at 30% opacity. This maintains the clean, academic aesthetic without cluttering the UI.

### The Rich Text Editor (Academic Style)
*   **Canvas:** Use `surface-container-lowest` (#ffffff).
*   **Toolbar:** Floating "Glass" style using `backdrop-blur`.
*   **Typography:** Default to `body-lg` (Inter, 1rem) with a 1.6 line-height to mimic the readability of a published paper.

### Sidebar Lists
*   **Standard:** No dividers. Use `spacing.2` for vertical padding.
*   **Active State:** Use a soft-pill background of `secondary-container` (#d5e0f7) with `on-secondary-container` (#586377) text.
*   **Indicator:** A 4px vertical "tab" of `primary` (#002045) on the far left of the active item.

### Cards & Data Tables
*   **Constraint:** Forbid the use of horizontal or vertical divider lines. 
*   **Separation:** Use alternating row fills of `surface-container-low` (#f1f4f6) or simply rely on `spacing.4` to define the grid.

### Status Chips
*   **Success (Academic Standing):** `tertiary-container` (#003e29) with `on-tertiary-container` (#39b282) text. Use for "Approved" or "Passing."
*   **Warning:** `amber-yellow` logic (via custom tokens) for "Probation" or "Pending."

## 6. Do's and Don'ts

### Do
*   **Do** use `spacing.10` or `spacing.12` to separate major content blocks to create an "airy" editorial feel.
*   **Do** use `tertiary-fixed` (#85f8c4) as a highlight color for innovative data points.
*   **Do** ensure all interactive elements have a clear `surface-container-high` hover state.

### Don't
*   **Don't** use pure black (#000000) for text. Always use `on-surface` (#181c1e) to keep the contrast sophisticated rather than jarring.
*   **Don't** use standard "Drop Shadows." Only use the Ambient Glow or Tonal Layering.
*   **Don't** use hard 1px lines to separate sidebar items; let the whitespace do the work.