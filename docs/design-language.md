# MAGFest Budget App - Design Language Guide

Created: 2026-02-26
Status: Living Document

This document defines the design patterns and conventions used throughout the application. All new templates should follow these guidelines.

---

## Table of Contents

1. [Button Placement](#button-placement)
2. [Section & Card Headers](#section--card-headers)
3. [Pills & Badges](#pills--badges)
4. [Navigation](#navigation)
5. [Forms](#forms)
6. [Callouts & Alerts](#callouts--alerts)
7. [Text Hierarchy](#text-hierarchy)
8. [Color Tokens](#color-tokens)
9. [Spacing](#spacing)

---

## Button Placement

### Principle
**Top-right header area is for management/admin actions. Inline buttons are for editing specific content.**

### Patterns

#### Page Header Actions
Actions that manage the entity or apply to the whole page go in the top-right:
```html
<div style="display: flex; justify-content: space-between; align-items: flex-start;">
  <div>
    <h1>Page Title</h1>
    <div class="muted">Subtitle or metadata</div>
  </div>
  <div style="display: flex; gap: 8px; align-items: center;">
    <!-- Role badges first -->
    <span class="pill pill-info">Department Head</span>
    <!-- Management actions -->
    <a class="btn" href="...">Manage Members</a>
  </div>
</div>
```

#### Section Header Actions
Actions that add items to a section go in the section header:
```html
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
  <h3 style="margin: 0;">Section Title</h3>
  <a class="btn btn-primary" href="...">+ Add Item</a>
</div>
```

#### Inline Edit Actions
Edit buttons for specific content sections go inline with that section:
```html
<section class="card">
  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
    <h4 style="margin: 0;">Department Info</h4>
    <a class="btn" href="...">Edit</a>
  </div>
  <!-- Content here -->
</section>
```

#### Form Button Order
Primary action first, cancel second, destructive/admin actions pushed right:
```html
<div class="btn-row" style="margin-top: 20px;">
  <button class="btn btn-primary" type="submit">Save Changes</button>
  <a class="btn" href="...">Cancel</a>
  <!-- Destructive actions pushed right -->
  <form method="post" action="..." style="margin-left: auto;">
    <button class="btn btn-danger" type="submit">Archive</button>
  </form>
</div>
```

---

## Section & Card Headers

### Standard Section Header
```html
<h3 style="margin: 0 0 12px 0;">Section Title</h3>
<div class="muted" style="margin-bottom: 16px;">
  Optional description of what this section contains.
</div>
```

### Section Header with Action
```html
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
  <h3 style="margin: 0;">Section Title</h3>
  <a class="btn btn-primary" href="...">+ Add Item</a>
</div>
```

### Card with Header
```html
<div class="card">
  <h4 style="margin: 0 0 12px 0;">Card Title</h4>
  <!-- Card content -->
</div>
```

### Card with Header and Action
```html
<div class="card">
  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
    <h4 style="margin: 0;">Card Title</h4>
    <a class="btn" href="...">Edit</a>
  </div>
  <!-- Card content -->
</div>
```

---

## Pills & Badges

### Base Classes
Use semantic class names for consistent styling:

| Class | Use Case | Colors |
|-------|----------|--------|
| `pill` | Default/neutral | Gray background |
| `pill-draft` | Draft status | Light gray |
| `pill-submitted` | Submitted/pending | Light blue |
| `pill-approved` | Approved/success | Light green |
| `pill-needs` | Needs attention | Light yellow/orange |
| `pill-rejected` | Rejected/error | Light red |
| `pill-info` | Informational badge | Blue |

### Usage Examples
```html
<!-- Status pills -->
<span class="pill pill-draft">Draft</span>
<span class="pill pill-submitted">Under Review</span>
<span class="pill pill-approved">Approved</span>
<span class="pill pill-needs">Needs Info</span>
<span class="pill pill-rejected">Rejected</span>

<!-- Role badges -->
<span class="pill pill-info">Department Head</span>
<span class="pill" style="background: #f3e8ff; color: #7c3aed;">Division Head</span>

<!-- Permission indicators -->
<span class="pill" style="background: #e9f7ef; font-size: 0.7rem;">Can Edit</span>
<span class="pill" style="background: #dbeafe; font-size: 0.7rem;">View Only</span>
```

### Status with friendly_status()
Always use the `friendly_status()` helper for user-facing status text:
```html
<span class="pill {{ status_pill_class }}">{{ friendly_status(status) }}</span>
```

---

## Navigation

### Back Links
Use at the top of pages, with left arrow:
```html
<div class="muted" style="margin-bottom: 12px;">
  <a href="{{ url_for('...') }}">&larr; Back to [Context]</a>
</div>
```

### Bottom Navigation
Use `.btn-row` for page-level navigation at bottom:
```html
<div class="btn-row" style="margin-top: 24px;">
  <a class="btn" href="{{ url_for('home.index') }}">Back to Home</a>
</div>
```

### Tabs
For organizing related content within a page:
```html
<div class="tab-row" style="display: flex; gap: 4px; margin-bottom: 16px;">
  <button class="tab active" data-tab="details">Details</button>
  <button class="tab" data-tab="lines">Lines <span class="badge">5</span></button>
  <button class="tab" data-tab="comments">Comments</button>
</div>

<div class="tab-content active" id="tab-details">...</div>
<div class="tab-content" id="tab-lines">...</div>
<div class="tab-content" id="tab-comments">...</div>
```

---

## Forms

### Field Structure
```html
<div style="margin-bottom: 16px;">
  <label for="field_id" style="display: block; font-weight: 600; margin-bottom: 6px;">
    Field Label <span style="color: red;">*</span>
  </label>
  <input type="text" id="field_id" name="field_name" required style="width: 100%;">
  <div class="muted small" style="margin-top: 4px;">
    Helper text explaining the field.
  </div>
</div>
```

### Two-Column Grid
```html
<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
  <div><!-- Field 1 --></div>
  <div><!-- Field 2 --></div>
</div>
```

### Full-Width Field in Grid
```html
<div style="grid-column: 1 / -1;">
  <!-- Full width field -->
</div>
```

### Textarea Sizing
- **Description fields**: `rows="3"`
- **Notes/comments**: `rows="3"`
- **Short notes**: `rows="2"`

### Button Row
```html
<div class="btn-row" style="margin-top: 20px;">
  <button class="btn btn-primary" type="submit">Save Changes</button>
  <a class="btn" href="...">Cancel</a>
</div>
```

### Checkbox with Description
```html
<label style="display: flex; gap: 8px; align-items: flex-start; font-weight: normal;">
  <input type="checkbox" name="field" value="1" style="margin-top: 3px;">
  <div>
    <strong>Checkbox Label</strong>
    <div class="muted small">Description of what this checkbox does.</div>
  </div>
</label>
```

---

## Callouts & Alerts

### Classes
| Class | Use Case | Appearance |
|-------|----------|------------|
| `callout` | Base container | Default styling |
| `callout-info` | Information | Blue left border |
| `callout-success` | Success/approval | Green left border |
| `callout-warning` | Warning/attention | Yellow left border |
| `callout-danger` | Error/rejection | Red left border |
| `callout-action` | Action required | Yellow with emphasis |

### Structure
```html
<div class="callout callout-warning" style="margin-bottom: 16px;">
  <strong>Action Required</strong>
  <div class="muted" style="margin-top: 4px;">
    Description of what the user needs to do.
  </div>
  <!-- Optional action buttons -->
  <div style="margin-top: 12px;">
    <a class="btn btn-primary" href="...">Take Action</a>
  </div>
</div>
```

### Inline Styles (until CSS classes exist)
```html
<!-- Info -->
<div class="callout" style="background: #e7f3fe; border-left: 4px solid #2196f3;">

<!-- Success -->
<div class="callout" style="background: #f0fdf4; border-left: 4px solid #059669;">

<!-- Warning -->
<div class="callout" style="background: #fef3c7; border-left: 4px solid #fbbf24;">

<!-- Danger -->
<div class="callout" style="background: #fee2e2; border-left: 4px solid #dc3545;">
```

---

## Text Hierarchy

### Headings
- `<h1>`: Page titles
- `<h2>`: Major sections
- `<h3>`: Subsections (margin: 0 0 12px 0)
- `<h4>`: Card titles (margin: 0 0 12px 0)

### Muted Text
- `.muted`: Secondary text, metadata, descriptions
- `.muted.small`: Helper text below inputs, fine print
- Always use `margin-top: 4px` for helper text below inputs
- Use `margin-top: 8px` for section descriptions

### Emphasis in Muted Text
```html
<div class="muted">
  <strong>Important term</strong> followed by explanation.
</div>
```

---

## Color Tokens

### Status Colors
| Status | Background | Text | Border |
|--------|------------|------|--------|
| Draft | #f3f4f6 | #4b5563 | - |
| Submitted | #dbeafe | #1e40af | - |
| Approved | #e9f7ef | #059669 | - |
| Needs Info | #fef3c7 | #92400e | - |
| Rejected | #fee2e2 | #991b1b | - |

### Role Colors
| Role | Background | Text |
|------|------------|------|
| Department Head | #fef3c7 | #92400e |
| Division Head | #f3e8ff | #7c3aed |
| Admin | #dbeafe | #1e40af |

### Action Colors
| Type | Class | Background |
|------|-------|------------|
| Primary | `btn-primary` | Blue |
| Secondary | `btn` | Gray/outline |
| Danger | `btn-danger` | Red |

---

## Spacing

### Standard Values
- **4px**: Tight spacing (between label and input, pill margins)
- **8px**: Small gaps (between buttons, between inline elements)
- **12px**: Standard margin (after headings, between form sections)
- **16px**: Section padding (card padding, major spacing)
- **20px**: Form button row margin-top
- **24px**: Page section margins

### Common Patterns
```css
/* Heading to content */
margin: 0 0 12px 0;

/* Form field spacing */
margin-bottom: 16px;

/* Button row */
margin-top: 20px;

/* Section spacing */
margin-top: 24px;
margin-bottom: 24px;

/* Helper text */
margin-top: 4px;

/* Gap between inline elements */
gap: 8px;
```

---

## Component Checklist

When creating new templates, verify:

- [ ] Page title uses `<h1>`
- [ ] Back link at top with `&larr;`
- [ ] Section headers use `<h3>` with proper margins
- [ ] Action buttons placed according to placement rules
- [ ] Pills use semantic class names
- [ ] Callouts use appropriate color classes
- [ ] Form fields have labels with `font-weight: 600`
- [ ] Form fields have `.muted.small` helper text where needed
- [ ] Button rows follow primary/secondary/destructive order
- [ ] `.muted` used consistently for secondary text
- [ ] Spacing follows standard values

---

## Future Improvements

### Priority 1 (High Impact)
1. Create CSS classes for all pill variants
2. Create CSS classes for callout color variants
3. Standardize button placement across all forms
4. Create reusable form field macros

### Priority 2 (Medium Impact)
1. Remove inline styles for colors - use CSS classes
2. Create tab component template for reuse
3. Standardize navigation patterns

### Priority 3 (Low Impact)
1. Standardize textarea sizing
2. Document placeholder text patterns
3. Create breadcrumb component for deep pages
