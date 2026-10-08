# Report design

Six pages. Each one answers one stakeholder's question, and every visual uses the measures in `measures.dax`. Save the finished report as a **Power BI Project (`.pbip`)** in this folder, so the report and model definitions are versioned in Git as text.

## 1. Overview (finance and procurement leadership)

- **KPI cards:** Spend (GBP) with YoY %, PR-backed %, OTIF %, First-time Match %, GR/IR Over 90 Days (GBP), Paid On Time %
- **Line:** monthly Spend vs Spend PY
- **Bar:** spend by material group, coloured by spend type (Direct / Indirect)
- **Callout table:** "what needs attention": the six figures from the README findings, each with a drill-through to its page

## 2. Buying compliance (procurement director)

- **Matrix:** purchasing group × (No-PR %, After-the-fact %, After-the-fact Spend)
- **Column:** after-the-fact PO items by month, split by purchasing group
- **Line:** Avg PR-to-PO Days by month
- **Drill-through table:** after-the-fact PO lines with supplier, PO date, first invoice date and value

## 3. Supplier performance (supply chain)

- **Scatter:** spend (x) vs OTIF % (y) per supplier, with a constant line at 70% OTIF. The bottom-right quadrant holds high-spend, low-OTIF suppliers.
- **Table:** supplier ranking with On-time %, OTIF %, Short-delivery Gap (pts), Avg PO-to-GR Days, conditional formatting
- **Column:** Short-delivery Gap by material group

## 4. GR/IR (financial controller)

- **Stacked bar:** GR Not Invoiced (GBP) by `grir_age_bucket` and purchasing group
- **Table:** open GR/IR lines over 90 days: PO, supplier, last receipt, balance (export for the month-end clean-up)
- **Card pair:** GR Not Invoiced vs Invoiced Not Received

## 5. Invoice and payment control (accounts payable)

- **Line:** First-time Match % by month
- **Table:** duplicate suspects: supplier, both invoice numbers (`invoice_key`, `duplicate_of_invoice`), both references, amount, paid flag
- **Histogram:** payment date minus due date (days early / late)
- **Cards:** Open Payables, Overdue Payables, Paid Early Value

## 6. Data health (platform owners)

From `gold_dq_results` and `bronze_load_log`:

- **Cards:** last load time, checks passed / total
- **Table:** latest run's checks with pass/fail icons
- **Line:** rows loaded per table per run

## Model settings

- Storage mode **Direct Lake** on the `lh_p2p` lakehouse
- Relationships: dimension 1 → * fact, single direction. `'Supplier Invoice'[posting_date]` → `'Date'[date]` is active; add `document_date` as an inactive relationship for `USERELATIONSHIP`
- Mark `'Date'` as the date table; sort `month_name` by `month`
- Hide keys and the `is_*` flag columns from report view; expose measures only
- Display folders: Spend & Compliance, Delivery, GR/IR, Invoices & Payments
