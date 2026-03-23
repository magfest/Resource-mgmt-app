# Budget App - Post-Review Implementation Plan

> **STATUS UPDATE - March 2026**
> - **Phase 1:** COMPLETE - All quick wins (copy, labels, help text) implemented
> - **Phase 2 Process/Data Tasks:** COMPLETE - These were admin UI configuration and documentation tasks, not code
> - **Phase 2 Code Work & Phase 3 Features:** See `docs/plan-outstanding-march2026.md` for current consolidated tracking
>
> This document remains the authoritative reference for detailed specifications of Phase 2/3 features.

## Context
The team completed a feedback/demo session and identified pain points across terminology, guidance, approval workflows, hotel wizard UX, event-specific overrides, reporting, and deadline enforcement. This plan addresses all feedback items, phased as **quick wins first, then deep work**.

## Decisions Made
- **Terminology**: "Approval Group" -> **"Reviewer Group"**
- **Deadlines**: Soft block + budget admin override
- **Hotel wizard**: Keep all fields, add better help text/guidance
- **Phasing**: Quick wins (copy/help text) first, then deep workflow/reporting work

---

## Phase 1: Quick Wins (Copy, Labels, Help Text) -- COMPLETED

> **Status: All Phase 1 tasks implemented.** 34 files changed, app verified loading.
> Verified: zero remaining "Approval Group", "AG Approved", or "AG Recommended" text in templates.

### 1.1 UX_COPY_APPROVAL_TERMS - DONE

Renamed across all templates, reports, CSV exports, email, and Python dataclasses:

| Old Label | New Label | Where |
|-----------|-----------|-------|
| Approval group(s) | Reviewer group(s) | All templates, admin pages, dispatch, data upload docs |
| AG Approved | Reviewer Recommended | Report columns, summary cards, macros |
| AG Recommended | Reviewer Recommended | Line review pages |
| AG APPROVED (badge) | RECOMMENDED | Line status pills in tables |
| AG REJECTED (badge) | REVIEWER REJECTED | Line status pills |
| Recently Decided | Recently Reviewed | Approvals dashboard |
| Approval Dashboard | Review Dashboard | Approvals dashboard title |
| Approval Queue | Review Queue | Work item detail nav |

**Python rename:** `PipelineTotals.ag_approved_cents` -> `reviewer_recommended_cents` in `report_utils.py` and all 5 consuming files.

**CSV export headers** updated in `ledger_report.py`, `department_report.py`, `workload_report.py`.

### 1.2 UX_COPY_SUITE_VERBIAGE - DONE

Added disambiguation help text in `work_item_edit.html` hotel purpose section:
> "Not sure which to pick? Department operations is for rooms essential to your department's function. Staff crash space is for optional social/sleeping suites."

### 1.3 HELP_BADGES_FIXED_COSTS - DONE

Added info banner with `bi-info-circle` icon in `work_item_edit.html` fixed costs tab:
> "Badge and comp costs shown here are for planning and informational purposes only. These are not directly charged to your department's budget."

### 1.4 HELP_HOTEL_WIZARD - DONE

- Guidance banner at top of hotel wizard in `work_item_edit.html`
- Early/late arrival help text added

### 1.5 HELP_NEW_FIELDS - DONE

Added inline help text below confidence and frequency dropdowns in `line_form.html`.

### 1.6 HELP_HOTEL_FUTURE_FEATURES - DONE

Added future features note at bottom of hotel wizard in `work_item_edit.html`.

---

## Phase 2: Deep Work (Workflows, Overrides, Reporting, Deadlines)

> **Audit note (2026-03-08):** After comparing each item against the codebase, many Phase 2 items are already implemented or are data/process tasks, not code tasks. Reorganized below.

### Phase 2 Code Changes (Requires Development)

#### 2.4 DEADLINE_POLICY - Soft Block + Override
**Status:** Not started — model field exists, enforcement logic missing

The `EventCycle.submission_deadline` field exists and is populated via admin UI, but no code checks it during submission. `work_item_submit()` in `app/routes/work/work_items/actions.py` validates status/lines but has zero deadline enforcement.

**Code needed:**
- Add deadline check in submission route (`actions.py`): if past deadline, block non-admins with flash message
- Budget admins (ROLE_WORKTYPE_ADMIN, ROLE_SUPER_ADMIN) bypass the block
- Add approaching-deadline warning banner on `department_home.html` (e.g., within 7 days)

**Files**: `app/routes/work/work_items/actions.py`, `app/templates/budget/department_home.html`

#### 2.5 SUPPLEMENTAL_FLOW - UI Clarity & Reason Field
**Status:** Core flow works, UI needs polish

Supplemental creation is fully functional (`create.py` lines 115-219, "SUP-" prefix, same pipeline). What's missing is UX:

**Code needed:**
- Add optional `reason` text field to WorkItem model (or use existing description field)
- Update supplemental creation template to collect reason
- Label supplementals as "Supplemental #N - [date] - [reason]" in list views
- Add `request_kind` filter to report queries in `report_utils.py` so primary vs. supplemental can be separated

**Files**: `app/models/workflow.py`, `app/routes/work/work_items/create.py`, supplemental creation template, `app/routes/admin_final/report_utils.py`

#### 2.6 REPORTING - Primary vs. Supplemental Breakdown
**Status:** 4 existing reports are solid; one gap worth coding

The only actionable code gap is adding a `request_kind` filter to existing reports so users can see primary vs. supplemental totals separately. Cross-event comparison is a "nice to have" but deferred — it's better addressed by the Historical P&L work in Phase 3.

**Code needed:**
- Add `request_kind` filter dropdown to department report and ledger report
- Update `report_utils.py` queries to filter by primary/supplemental

**Files**: `app/routes/admin_final/department_report.py`, `app/routes/admin_final/ledger_report.py`, `app/routes/admin_final/report_utils.py`

---

### Phase 2 Process / Data / Documentation (No Code)

#### 2.1 EXPENSE_OVERRIDES_EVENT - Populate Override Data ✅ Code Complete
**Type:** Data entry via existing admin UI

The `ExpenseAccountEventOverride` model and resolution logic (`get_effective_fixed_cost_settings()` in `expense_accounts.py`) are fully implemented. This is purely a data population task:
- Use the admin UI to create override records for hotel rates per event
- Set overrides for badges, appearance fees, other annually-changing fixed costs
- Verify the hotel wizard reflects correct totals after data entry

#### 2.2 FIXED_COST_IMPORT - Populate Fixed Cost Catalog ✅ Code Complete
**Type:** Data entry via existing admin UI

`ExpenseAccount` fully supports `is_fixed_cost`, `default_unit_price_cents`, `unit_price_locked`, frequency defaults. Query helpers exist (`get_fixed_cost_expense_accounts()`, etc.). This is a data task:
- Create/update expense account records via admin UI with fixed-cost settings
- Extract values from prior budget spreadsheets
- Mark annually-changing values for override via event overrides (2.1)

#### 2.3a APPROVAL_ROLE_DOC - Document Role Matrix ✅ Code Complete
**Type:** Documentation

Roles are already enforced correctly in route decorators across the app (`require_budget_admin()`, `require_dispatch_admin()`, portfolio edit permissions, reviewer group membership checks). This is a documentation task:
- Write down the role → rights matrix for team reference
- Confirm with stakeholders that the enforced permissions match expectations

| Role | Rights (already enforced in code) |
|------|-----------------------------------|
| Department head | Edit own dept budgets, manage dept members |
| Division head | See/manage all depts in division |
| Reviewer group member | Recommend amounts, request info on assigned lines |
| Budget admin | See all budgets, dispatch, finalize |
| Super admin | Full control including config |

#### 2.3b APPROVAL_STATE_VISIBILITY ✅ Code Complete
**Type:** Verification only

`friendly_status()` in `formatting.py` already maps all active statuses to user-friendly labels (Draft, Waiting for Assignment, Under Review, Info Requested, Approved, Finalized, Paused). No code change needed. Verify labels make sense to the team and adjust wording if desired.

#### 2.3c APPROVAL_GROUP_UI ✅ Code Complete (Phase 1)
**Type:** Verification only

Terminology was updated across all templates in Phase 1. Dashboard already says "reviewer groups," uses "Recommended" not "Approved" for reviewer actions, and shows "Recently Reviewed." Verify nothing was missed.

#### 2.7 MULTI_EVENT_STRUCTURE - Misc Events Setup ✅ Code Complete
**Type:** Admin UI configuration + documentation

No code changes needed. The event cycle, department, and work portfolio models support this already:
- Create "Miscellaneous Events" event cycle via admin UI
- Create/activate departments for external events (Awesome Con, Setsucon, etc.)
- Assign members to those department/event combinations
- Document the "department activated by member assignment" pattern for future admins

#### 2.8a UI_QUANTITY_DECIMALS ✅ Working Correctly
**Type:** No action needed

Quantity is `Numeric(12, 3)` and validation in `lines.py` correctly parses as Decimal, rejects non-numeric, requires > 0. Fractional quantities are intentional (partial room nights, etc.). No change needed.

#### 2.8b UI_QUICK_REVIEW_FINALIZE ✅ Working Correctly
**Type:** No action needed

Per-line approve/reject with optional amount override is fully implemented in `admin_final/reviews.py`. Finalize logic in `helpers.py` correctly auto-approves pending lines at requested amount and sets final status. Working as designed.

#### 2.9 DOCS - Lifecycle Documentation
**Type:** Documentation

- Diagram the full budget lifecycle: Draft → Submit → Dispatch → Reviewer Group → Kickback/Recommendation → Final Approval → Finalized → Supplemental
- Document event/division/department/member setup steps
- Can be a markdown doc or admin help page

---

## Phase 3: New Feature Requests (Team Feedback Round 2)

> Added 2026-03-08. These items came from the broader team (finance, leadership, department heads). No coding yet — this is the planning phase.

### Priority Order

| # | Item | Size | Priority | Rationale |
|---|------|------|----------|-----------|
| 3.1 | Required dropdowns on line form | Small | P1 - Do First | Quick fix, prevents bad data now |
| 3.4 | Admin can add lines to budget requests | Medium | P2 - High | Unblocks admin workflows, prerequisite for 3.5 |
| 3.5 | Interdepartmental spend tracking | Large | P3 - High | Core workflow change requested by multiple teams |
| 3.2 | Income accounts (revenue lines) | Large | P4 - Medium | Big model change, but merch team needs it for planning |
| 3.3 | Historical P&L import & reporting | XL | P5 - Medium | High value for finance, but large scope and can be phased |

---

### 3.1 REQUIRED_LINE_DROPDOWNS - Make Priority, Confidence, Frequency Required

**Size:** Small (1-2 hours)
**Status:** Not started

#### Problem
Three dropdowns in `line_form.html` currently show "(Optional)" as the first option:
1. **Priority** (`priority_id`, line 81)
2. **Unit Cost Confidence** (`confidence_level_id`, line 95)
3. **Frequency** (`frequency_id`, line 112)

The team says all three are required for proper review. Reviewers need to know priority, confidence level, and frequency to make informed recommendations.

#### Plan
- **Template** (`app/templates/budget/line_form.html`): Change placeholder text from "(Optional)" to "(Select one)" or similar, mark fields visually required
- **Backend** (`app/routes/work/lines.py`): Add server-side validation in the POST handler — reject if any of the three are missing/empty. Flash a clear error message
- **Client-side**: Add `required` attribute to the `<select>` elements for immediate browser-level feedback

#### Wireframe
```
No visual change to layout. Dropdowns look the same but:
- Placeholder changes: "(Optional)" → "(Required - select one)"
- Red asterisk (*) added to labels
- Submit blocked if any are empty
- Flash: "Priority, confidence, and frequency are required for all budget lines."
```

#### Risks
- Existing draft lines with null values — need a migration/data decision: backfill or grandfather existing drafts?
- Recommendation: Enforce going forward only. Existing drafts can be submitted as-is but new/edited lines must comply.

---

### 3.2 INCOME_ACCOUNTS - Revenue / Income Line Support

**Size:** Large (multi-sprint)
**Status:** Not started — needs design decisions

#### Problem
The system is entirely expense-focused. The merch team (and potentially others) generate revenue and leadership wants to see estimated income alongside expenses to get a net budget picture. Example: merch estimates $X in sales revenue per event.

#### Key Design Decisions Needed

1. **Where does income live?**
   - **Option A (Recommended):** Add `account_type` enum field to `ExpenseAccount` model (`EXPENSE` | `INCOME`). Rename model later or keep as-is with the understanding that "ExpenseAccount" is really "BudgetAccount."
   - **Option B:** Create a separate `IncomeAccount` model. Cleaner naming but duplicates structure and complicates queries.
   - **Recommendation:** Option A — least disruption. Add `account_type = Column(Enum('EXPENSE', 'INCOME'), default='EXPENSE')`.

2. **How do income lines flow through the pipeline?**
   - Income lines should follow the same Draft → Submit → Review → Finalize pipeline
   - Reviewers need to validate revenue estimates just like expenses
   - Final approved amount on an income line = approved revenue forecast

3. **How is income displayed?**
   - Budget request detail: Separate "Revenue Lines" section below expense lines, or mixed in with a clear visual indicator (green vs. red, +/- prefix)?
   - Reports: Need a net summary row (Expenses - Income = Net Budget)
   - Department home: Show "Estimated Revenue" alongside "Total Requested"

#### Plan — Phased

**Phase A: Model + Admin Setup**
- Add `account_type` enum to `ExpenseAccount` model (default `EXPENSE`)
- Migration: all existing accounts default to `EXPENSE`
- Admin expense account page: Add toggle/dropdown for account type
- Admin can create income accounts (e.g., "Merch Sales Revenue", "Registration Revenue")

**Phase B: Line Form + Request Display**
- `line_form.html`: When user selects an income-type expense account, visually indicate it (green highlight, "Revenue" badge)
- `work_item_edit.html` / `work_item_detail.html`: Group and subtotal income lines separately
- Display: "Total Expenses: $X | Estimated Revenue: $Y | Net: $Z"

**Phase C: Reporting**
- All four reports need income columns and net calculations
- Department report: Add "Revenue", "Net" columns
- Ledger report: Income accounts grouped separately, net total row
- CSV exports: Include income and net columns

#### Wireframe — Budget Request Detail View
```
┌─────────────────────────────────────────────────────┐
│ Budget Request: Merch - Super MAGFest 2026          │
├─────────────────────────────────────────────────────┤
│                                                     │
│ EXPENSE LINES                                       │
│ ┌───────────────┬────────┬─────────┬──────────────┐ │
│ │ Expense       │ Qty    │ Unit $  │ Total        │ │
│ ├───────────────┼────────┼─────────┼──────────────┤ │
│ │ T-Shirt Stock │ 500    │ $8.00   │ $4,000.00    │ │
│ │ Booth Setup   │ 1      │ $200.00 │ $200.00      │ │
│ └───────────────┴────────┴─────────┴──────────────┘ │
│                          Total Expenses: $4,200.00  │
│                                                     │
│ REVENUE LINES (Estimated Income)                    │
│ ┌───────────────┬────────┬─────────┬──────────────┐ │
│ │ Account       │ Qty    │ Unit $  │ Total        │ │
│ ├───────────────┼────────┼─────────┼──────────────┤ │
│ │ Merch Sales   │ 1      │$6,000.00│ $6,000.00    │ │
│ └───────────────┴────────┴─────────┴──────────────┘ │
│                        Estimated Revenue: $6,000.00 │
│                                                     │
│              ═══════════════════════════             │
│                    NET BUDGET: -$1,800.00            │
│              (Revenue exceeds expenses)             │
└─────────────────────────────────────────────────────┘
```

#### Risks & Considerations
- **Sign convention**: Decide early — are income lines stored as positive cents and subtracted in display, or stored as negative cents? Recommendation: Store as positive, flag via `account_type`, subtract in display/reports. Simpler math, clearer data.
- **Approval routing**: Income accounts still need reviewer group assignment. Merch revenue estimates should probably route to finance reviewers.
- **Naming**: The `ExpenseAccount` model name becomes misleading. Consider a rename to `BudgetAccount` as part of this work, or accept the tech debt and document it.
- **Scope creep**: Don't try to build actual income tracking/invoicing. This is *estimated revenue for budget planning purposes only*.

---

### 3.3 HISTORICAL_PL_IMPORT - P&L Import & Top-Line Reporting

**Size:** XL (multi-sprint, phased)
**Status:** Not started — needs design decisions

#### Problem
Finance wants historical context when reviewing budgets. Each department has a P&L from the accounting system (QuickBooks-style export). Currently there's no way to see "last year this department spent $X" alongside "this year they're requesting $Y."

#### Example Data Analyzed
`Example_Data/Jam Clinic P&L.xlsx` — Structure:
- **Columns**: Date, Name (vendor), Department, Class (event), Memo/Description, Amount
- **Hierarchy**: Ordinary Income/Expenses → Expenses → Division → Category → Line items → Category totals → Division totals
- **Contains**: ~26 actual transactions, category subtotals, budget vs. actual variance section
- **Scope**: Single department (Jam Clinic), single event (Super MAGFest)

#### Key Design Decisions Needed

1. **What level of detail do we import?**
   - **Option A (Recommended for MVP):** Category-level summary only (e.g., "Supplies: $2,671", "Tech Equipment: $5,218"). Map categories to our expense accounts where possible.
   - **Option B:** Full line-item detail. Much more data, much more complexity, questionable value for budget planning purposes.
   - **Recommendation:** Start with Option A. Finance gets their comparisons; we avoid massive data imports.

2. **Where does imported data live?**
   - New model: `HistoricalBudgetSummary` with fields like:
     - `department_id`, `event_cycle_id` (or `fiscal_year`)
     - `expense_account_id` (nullable — for unmapped categories)
     - `category_label` (original P&L category name)
     - `actual_amount_cents`
     - `budgeted_amount_cents` (if available in P&L)
     - `source_file`, `imported_at`, `imported_by_id`
   - This is read-only reference data — no workflow, no approval pipeline

3. **How is it surfaced?**
   - Reports: New "Budget vs. Actuals" report comparing current request to historical actuals
   - Department home: "Last year's actual: $X" context line
   - Review screen: Reviewer sees historical context when evaluating a line

#### Plan — Phased

**Phase A: Model + Import Tool**
- Create `HistoricalBudgetSummary` model
- Build admin-only import page: upload XLSX, preview parsed data, confirm import
- Parser handles the hierarchical P&L format (detect category rows vs. total rows vs. transaction rows)
- Map P&L categories to existing expense accounts where names match; leave unmapped ones with `category_label` only
- Import creates summary-level records (one row per category per department per event)

**Phase B: Reports**
- New report: **"Historical Comparison"**
  - Columns: Department | Expense Category | Prior Year Actual | Current Year Budgeted | Current Year Approved | Variance
  - Filterable by event, department, division
  - CSV export
- Enhance existing department report: Add optional "Prior Year Actual" column when historical data exists

**Phase C: Contextual Display**
- Department home page: Show "Prior year actual spend" summary card when historical data exists
- Line review screen: When a reviewer is looking at a line for "Supplies", show "Last year actual for Supplies in this dept: $2,671"
- Budget request detail: Show historical comparison sidebar or expandable section

#### Wireframe — Historical Comparison Report
```
┌─────────────────────────────────────────────────────────────────────┐
│ Historical Budget Comparison — Super MAGFest                       │
│ [Event: Super MAGFest ▼] [Department: All ▼] [Export CSV]          │
├──────────────┬──────────────┬───────────┬───────────┬──────────────┤
│ Department   │ Category     │ 2025      │ 2026      │ Variance     │
│              │              │ Actual    │ Requested │              │
├──────────────┼──────────────┼───────────┼───────────┼──────────────┤
│ Jam Clinic   │ Supplies     │ $2,671    │ $3,100    │ +$429 (16%)  │
│ Jam Clinic   │ Tech Equip   │ $5,218    │ $4,800    │ -$418 (-8%)  │
│ Jam Clinic   │ Dues & Subs  │ $64       │ $64       │ $0 (0%)      │
│ Jam Clinic   │ TOTAL        │ $7,953    │ $7,964    │ +$11 (<1%)   │
├──────────────┼──────────────┼───────────┼───────────┼──────────────┤
│ Main Stage   │ A/V Rental   │ $12,400   │ $14,000   │ +$1,600 (13%)│
│ ...          │ ...          │ ...       │ ...       │ ...          │
└──────────────┴──────────────┴───────────┴───────────┴──────────────┘
```

#### Wireframe — Admin Import Page
```
┌─────────────────────────────────────────────────────┐
│ Import Historical P&L Data                          │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Event Cycle: [Super MAGFest 2025 ▼]                 │
│ Department:  [Jam Clinic ▼]                         │
│                                                     │
│ Upload File: [Choose .xlsx file]                    │
│                                                     │
│ [Parse & Preview]                                   │
│                                                     │
│ ┌─ Preview ───────────────────────────────────────┐ │
│ │ Found 3 categories:                             │ │
│ │  ✓ Supplies ($2,671.19) → mapped to "Supplies"  │ │
│ │  ✓ Tech Equipment ($5,218.33) → mapped to       │ │
│ │    "Tech Equipment"                             │ │
│ │  ⚠ Dues & Subscriptions ($63.60) → NO MATCH    │ │
│ │    [Map to: (Select account ▼)]                 │ │
│ │                                                 │ │
│ │ Total: $7,953.12                                │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ [Confirm Import]  [Cancel]                          │
└─────────────────────────────────────────────────────┘
```

#### Risks & Considerations
- **P&L format variability**: Different accounting exports may have different structures. The parser needs to be flexible or we standardize on one format.
- **Category mapping**: P&L categories won't match our expense accounts 1:1. Need a manual mapping step during import (shown in wireframe above).
- **Multi-year**: Eventually they'll want 2+ years of history. Model should support multiple years from the start.
- **Data ownership**: Imported P&L data is read-only reference. It should never be editable through the budget app — only re-importable.
- **This is NOT a real-time accounting integration.** It's a periodic bulk import for context. Set that expectation clearly.

---

### 3.4 ADMIN_ADD_LINES - Budget/Super Admins Can Add Lines to Requests

**Size:** Medium (1-2 days)
**Status:** Not started

#### Problem
Currently, only portfolio members (department staff) can add lines to a budget request, and only while in DRAFT status. Budget admins and super admins need to add lines — for example, adding a line the department forgot, or adding an income line on their behalf.

#### Key Design Decisions

1. **When can admins add lines?**
   - **Option A:** Only to DRAFT requests (same as department, just expanded permissions)
   - **Option B (Recommended):** To any non-finalized request. Admins sometimes need to add lines after submission (e.g., adding a forgotten fixed cost during review).
   - If added post-submission, the line enters the pipeline at the current stage (dispatched if request is dispatched, etc.)

2. **Audit trail?**
   - Lines added by admins should be clearly marked: "Added by [Admin Name] on [date]"
   - This distinguishes admin-added lines from department-requested lines in reviews

#### Plan

- **Permissions** (`app/routes/work/helpers/checkout.py`): Expand `can_add_lines` logic:
  ```
  can_add_lines = can_edit OR (is_budget_admin AND status != FINALIZED)
  ```
- **Route** (`app/routes/work/lines.py`): Allow admin roles to bypass the `require_work_item_edit()` check for line creation. Add `added_by_admin` flag or `added_by_user_id` field to `WorkLine` or `BudgetLineDetail`.
- **Template** (`app/templates/budget/work_item_edit.html`): Show "Add Line" button to admins even when request isn't in DRAFT
- **Display**: Admin-added lines get a small badge or note: "Added by admin" in the line list
- **Pipeline integration**: If request is already dispatched/under review, the new line should be auto-dispatched to the appropriate reviewer group based on its expense account routing

#### Wireframe — Admin View of Non-Draft Request
```
┌─────────────────────────────────────────────────────┐
│ Budget Request: Jam Clinic - Super MAGFest 2026     │
│ Status: Under Review                                │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Lines:                                              │
│ ┌──┬───────────────┬────────┬─────────┬───────────┐ │
│ │  │ Expense       │ Qty    │ Total   │ Status    │ │
│ ├──┼───────────────┼────────┼─────────┼───────────┤ │
│ │1 │ Supplies      │ 10     │ $500.00 │ Reviewing │ │
│ │2 │ Tech Equip    │ 2      │$1,200.00│ Reviewing │ │
│ │3 │ Venue Deposit │ 1      │ $300.00 │ Reviewing │ │
│ │  │ ↳ Added by S. Admin on 3/5     │           │ │
│ └──┴───────────────┴────────┴─────────┴───────────┘ │
│                                                     │
│ [+ Add Line] ← visible to budget/super admins      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### Risks
- **Notification**: Should the department be notified when an admin adds a line to their request? Probably yes — add a flash or email.
- **Approval routing**: Auto-dispatch of admin-added lines on an already-dispatched request needs careful handling. The line needs a `routed_approval_group_id` set based on the expense account's routing rules.
- **This is a prerequisite for 3.5 (interdepartmental spend)** — admins may need to add cross-department lines.

---

### 3.5 INTERDEPARTMENTAL_SPEND - Cross-Department Spend Tracking

**Size:** Large (multi-sprint)
**Status:** Not started — needs design decisions

#### Problem
Some departments request budget for items that another department actually executes the spend. Example: A programming department budgets for A/V equipment, but the A/V team actually purchases and manages it. Or a department budgets for merch, but the Merch team does the buying.

The requesting department needs to see: "This line was approved, but it will be spent by A/V team."
The spending department needs a report: "Here's everything other departments have approved for us to spend on their behalf."

#### Key Design Decisions

1. **How is interdepartmental spend flagged?**
   - Add `spending_department_id` (nullable FK to Department) on `BudgetLineDetail`
   - When null → normal spend (requesting dept = spending dept)
   - When set → the specified department handles the actual purchasing

2. **Who sets the spending department?**
   - **Option A:** Requester picks from a dropdown when adding the line ("Who will execute this spend?")
   - **Option B (Recommended):** Driven by expense account configuration. Certain expense accounts (e.g., "A/V Equipment Rental") are configured with a `default_spending_department_id`. When a department adds a line with that account, it auto-populates. Can be overridden.
   - **Hybrid:** Auto-populate from expense account config, but allow requester/admin to override.

3. **How does it affect approval flow?**
   - The line still belongs to the requesting department's budget request
   - It still routes through the normal reviewer group for that expense account
   - The spending department does NOT need to approve it in the budget system (they're just executing)
   - But the spending department needs visibility via reports

#### Plan — Phased

**Phase A: Model Changes**
- Add to `BudgetLineDetail`:
  - `spending_department_id` (nullable FK → Department)
- Add to `ExpenseAccount`:
  - `default_spending_department_id` (nullable FK → Department) — for auto-population
- Migration: All existing lines get `spending_department_id = NULL` (same dept = no cross-dept spend)

**Phase B: UI — Line Form**
- When expense account has a `default_spending_department_id`, auto-fill and show:
  ```
  "This expense will be executed by: [A/V Team]  [Change ▼]"
  ```
- If no default, show optional dropdown: "Spending department (if different): [Select ▼]"
- On budget request detail, lines with a different spending dept show a badge:
  ```
  "⇄ Spent by: A/V Team"
  ```

**Phase C: Department View — Requesting Side**
- On the requesting department's budget request detail, interdepartmental lines show clearly:
  ```
  Line: A/V Equipment Rental — $5,000 — APPROVED
  ⇄ To be spent by: A/V Team
  ```
- Summary card on department home: "Interdepartmental spend approved: $X (to be spent by other depts)"

**Phase D: Spending Department Report (New)**
- New report: **"Interdepartmental Spend Report"**
- Shows the spending department everything that other departments have approved for them to execute
- Filterable by event, spending department

#### Wireframe — Interdepartmental Spend Report
```
┌─────────────────────────────────────────────────────────────────────┐
│ Interdepartmental Spend Report — Super MAGFest 2026                │
│ [Spending Dept: A/V Team ▼] [Event: Super MAGFest ▼] [Export CSV]  │
├───────────────┬──────────────┬───────────┬───────────┬─────────────┤
│ Requesting    │ Expense      │ Approved  │ Status    │ Notes       │
│ Department    │ Account      │ Amount    │           │             │
├───────────────┼──────────────┼───────────┼───────────┼─────────────┤
│ Main Stage    │ A/V Rental   │ $8,000    │ Finalized │ 2 projectors│
│ Jam Clinic    │ A/V Rental   │ $2,500    │ Approved  │ PA system   │
│ Panels        │ A/V Rental   │ $3,200    │ Reviewing │ Mics + board│
├───────────────┼──────────────┼───────────┼───────────┼─────────────┤
│               │ TOTAL        │ $13,700   │           │             │
└───────────────┴──────────────┴───────────┴───────────┴─────────────┘
```

#### Wireframe — Line Form with Interdepartmental Indicator
```
┌─────────────────────────────────────────────────────┐
│ Add Budget Line                                     │
├─────────────────────────────────────────────────────┤
│ Expense Account: [A/V Equipment Rental ▼]           │
│ Spend Type:      [Rental ▼]                         │
│                                                     │
│ ┌─ Interdepartmental Spend ──────────────────────┐  │
│ │ This expense will be executed by: A/V Team      │  │
│ │ [Change spending department ▼]                  │  │
│ └────────────────────────────────────────────────┘  │
│                                                     │
│ Quantity: [___]   Unit Price: [$___]                 │
│ Priority: [(Required - select one) ▼]               │
│ Confidence: [(Required - select one) ▼]             │
│ Frequency: [(Required - select one) ▼]              │
│ Description: [________________________________]     │
│                                                     │
│ [Add Line]  [Cancel]                                │
└─────────────────────────────────────────────────────┘
```

#### Risks & Considerations
- **Budget attribution**: The spend counts against the *requesting* department's budget, not the spending department. The spending department just executes. This must be crystal clear in the UI and reports.
- **Spending department doesn't "approve" in the system**: They just get a report of what's coming. If they need to formally accept, that's a future workflow extension.
- **Report timing**: The interdepartmental spend report is most useful *after* finalization. During review, amounts may change. Consider showing only finalized lines by default with a toggle for in-progress.
- **Existing data**: No migration needed for existing lines — null `spending_department_id` means "normal, same-department spend."

---

## Implementation Sequencing

```
Phase 1: COMPLETED (Quick Wins)
  │
Phase 2: In Progress (Deep Work — existing items 2.1-2.9)
  │
Phase 3: New Feature Requests
  │
  ├─ 3.1 Required Dropdowns ─────────────────── Small, do anytime
  │
  ├─ 3.4 Admin Add Lines ────────────────────── Medium, prerequisite for 3.5
  │     │
  │     └─ 3.5 Interdepartmental Spend ──────── Large, depends on 3.4
  │
  ├─ 3.2 Income Accounts ────────────────────── Large, independent
  │     Phase A: Model ──→ Phase B: UI ──→ Phase C: Reports
  │
  └─ 3.3 Historical P&L Import ──────────────── XL, independent
        Phase A: Model+Import ──→ Phase B: Reports ──→ Phase C: Context
```

**Suggested sprint grouping:**
- **Sprint N:** 3.1 (required dropdowns) + 3.4 (admin add lines) + continue Phase 2 work
- **Sprint N+1:** 3.5 Phase A+B (interdepartmental model + UI) + 3.2 Phase A (income model)
- **Sprint N+2:** 3.5 Phase C+D (interdepartmental reports) + 3.2 Phase B (income UI)
- **Sprint N+3:** 3.3 Phase A (P&L import) + 3.2 Phase C (income reports)
- **Sprint N+4:** 3.3 Phase B+C (P&L reports + contextual display)

---

## Verification Plan

### Phase 1 Verification
- Search all templates for remaining "approval group" / "AG Approved" text - should be zero
- Visually verify help text appears correctly on hotel wizard, fixed costs, confidence/frequency fields
- Check email templates render with updated terminology
- Run existing tests (if any) to catch regressions

### Phase 2 Verification
- Test deadline enforcement: submit after deadline as dept head (should block), submit as budget admin (should succeed)
- Test expense account overrides: create override for event, verify hotel wizard shows correct rates
- Test supplemental flow: finalize primary, create supplemental with reason, verify it follows approval pipeline
- Test finalize behavior: finalize request with no per-line overrides, verify final_approved_amount populated correctly
- Test reports: verify renamed columns, supplemental breakdown if added
- Test quantity validation: enter fractional badge count (should reject), enter fractional monetary amount (should work)

### Phase 3 Verification
- **3.1**: Try submitting a line with empty priority/confidence/frequency — should be blocked. Existing drafts with null values can still be submitted.
- **3.2**: Create an income-type expense account via admin. Add an income line to a budget request. Verify reports show revenue, expenses, and net. Verify income lines flow through approval pipeline correctly.
- **3.3**: Import the Jam Clinic P&L example. Verify category mapping UI works. Verify historical comparison report shows correct data. Verify contextual display on review screens.
- **3.4**: As a budget admin, add a line to a submitted (non-draft) request. Verify the line is auto-dispatched. Verify the department sees the admin-added line. Verify audit trail shows who added it.
- **3.5**: Configure an expense account with a default spending department. Add a line using that account. Verify the interdepartmental indicator shows. Verify the spending department's report shows the line. Verify the requesting department's budget total includes the line.

---

## Key Files Reference

| Area | Files |
|------|-------|
| Models | `app/models/workflow.py`, `app/models/budget.py`, `app/models/org.py`, `app/models/constants.py` |
| Approval routes | `app/routes/approvals/dashboard.py`, `app/routes/approvals/reviews.py` |
| Admin final routes | `app/routes/admin_final/dashboard.py`, `app/routes/admin_final/reviews.py`, `app/routes/admin_final/helpers.py` |
| Work item routes | `app/routes/work/work_items/create.py`, `app/routes/work/work_items/edit.py`, `app/routes/work/work_items/view.py` |
| Line routes | `app/routes/work/lines.py` |
| Report routes | `app/routes/admin_final/ledger_report.py`, `app/routes/admin_final/department_report.py`, `app/routes/admin_final/workload_report.py`, `app/routes/admin_final/report_utils.py`, `app/routes/admin_final/report_exports.py` |
| Templates | `app/templates/approvals/dashboard.html`, `app/templates/budget/line_review.html`, `app/templates/budget/line_form.html`, `app/templates/budget/work_item_detail.html`, `app/templates/budget/work_item_edit.html`, `app/templates/budget/department_home.html` |
| Helpers | `app/routes/work/helpers/formatting.py`, `app/routes/work/helpers/expense_accounts.py`, `app/routes/work/helpers/checkout.py` |
| Email | `app/services/notifications.py`, `app/templates/email/*.txt` |
| Dispatch | `app/routes/dispatch/dashboard.py` |