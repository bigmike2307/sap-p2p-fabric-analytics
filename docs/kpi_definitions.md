# KPI definitions

Every KPI is calculated once in the gold layer (`fabric/notebooks/nb_03_gold_model.ipynb`) as a flag or value on a fact row. The DAX measures in `powerbi/measures.dax` only aggregate those columns. The rule constants are set at the top of notebook 03:

| Constant | Value | Meaning |
|---|---|---|
| `OTIF_TOLERANCE_DAYS` | 2 | a delivery up to 2 days after the agreed date still counts as on time |
| `IN_FULL_THRESHOLD` | 0.98 | receiving 98% of the ordered quantity counts as in full |
| `DUPLICATE_WINDOW_DAYS` | 90 | how far apart two postings can be and still be flagged as a duplicate |
| `EARLY_PAYMENT_DAYS` | 7 | paid more than 7 days before the due date = early |
| `GRIR_AGING_THRESHOLD_DAYS` | 90 | GR/IR older than this is reported as aged |

**Population.** PO KPIs exclude deleted items (`EKPO-LOEKZ = 'L'`). Invoice KPIs include every posted invoice (`RBKP-RBSTAT = '5'`). Amounts are in GBP at the monthly `M` rate valid on the PO date (spend) or the invoice posting date (payables).

## Spend and buying compliance

| KPI | Definition | Gold column(s) | SAP source |
|---|---|---|---|
| Spend (GBP) | Net PO item value translated to GBP | `net_amount_gbp` | EKPO-NETWR, EKKO-WAERS/BEDAT, TCURR |
| PR-backed rate | Share of PO items that reference a purchase requisition | `is_pr_backed` | EKPO-BANFN |
| Avg PR-to-PO days | PO date minus requisition release date (requisition date if never released), PR-backed items only | `pr_to_po_days` | EBAN-FRGDT/BADAT, EKKO-BEDAT |
| After-the-fact PO items | The earliest supplier invoice document date for the item is **before** the PO date: goods or services were ordered informally and the PO was raised to pay the invoice | `is_after_the_fact` | RBKP-BLDAT via RSEG, EKKO-BEDAT |
| Top-10 supplier spend share | Spend with the 10 largest suppliers ÷ total spend | (measure) | |

## Delivery performance

| KPI | Definition | Gold column(s) | SAP source |
|---|---|---|---|
| Due items | Items whose delivery date + tolerance is on or before the as-of date | `is_due` | EKET-EINDT |
| On-time rate | Due items whose **first** goods receipt (movement 101) was posted by delivery date + tolerance ÷ due items | `is_on_time` | EKBE (VGABE 1, BWART 101) |
| OTIF rate | Due items where net GR quantity posted by delivery date + tolerance ≥ 98% of the ordered quantity ÷ due items. Reversals (102) are netted. | `is_otif`, `gr_quantity_in_window` | EKBE (VGABE 1, SHKZG), EKPO-MENGE |
| Avg PO-to-first-GR days | First 101 posting date minus PO date | `po_to_first_gr_days` | EKBE, EKKO |

On-time minus OTIF shows what short deliveries cost: the supplier arrived on time but not with everything ordered.

## GR/IR

| KPI | Definition | Gold column(s) | SAP source |
|---|---|---|---|
| GR/IR balance | Σ GR clearing value − Σ IR clearing value per PO item, in local currency | `grir_balance_gbp` | EKBE-AREWR (signed by SHKZG) |
| GR not invoiced | Items with balance ≥ £0.01: goods received, invoice not yet posted | `grir_status = 'GR not invoiced'` | |
| Invoiced not received | Items with balance ≤ −£0.01: more invoiced than received (quantity variances, duplicates) | `grir_status = 'Invoiced not received'` | |
| GR/IR over 90 days | GR-not-invoiced balance where the last receipt is more than 90 days before the as-of date | `grir_age_bucket = '90+'` | EKBE-BUDAT |

`AREWR` is used rather than `DMBTR` because the GR/IR account clears at the goods-receipt value. Invoice price variances post to price-difference accounts and do not belong in the GR/IR balance.

## Invoices and payments

| KPI | Definition | Gold column(s) | SAP source |
|---|---|---|---|
| First-time match rate | 1 − share of invoices posted with a payment block (price or quantity variance outside tolerance) | `is_payment_blocked` | RBKP-ZLSPR |
| Duplicate invoice suspects | Invoice with the same supplier, the same **normalised** reference and the same gross amount as an earlier invoice posted within 90 days. The earlier invoice is in `duplicate_of_invoice` | `is_duplicate_suspect` | RBKP-LIFNR/XBLNR/RMWWR/BUDAT |
| Paid on time rate | Paid invoices cleared on or before the due date (baseline date + net days) ÷ paid invoices | `is_paid_on_time` | BSAK-AUGDT, RBKP-ZFBDT/ZBD1T |
| Paid early rate | Paid invoices cleared more than 7 days before the due date ÷ paid invoices | `is_paid_early` | |
| Avg days to pay | Clearing date minus invoice document date | `days_to_pay` | BSAK-AUGDT, RBKP-BLDAT |
| Open payables | Gross GBP value of invoices with no clearing by the as-of date | `is_open`, `gross_amount_gbp` | |
| Overdue open invoices | Open invoices whose due date has passed | `is_overdue` | |

**Reference normalisation.** Keep the digits of `XBLNR` and strip leading zeros, so `INV-004512`, `INV4512` and `4512` all become `4512`. If a reference has no digits, use it upper-cased with non-alphanumeric characters removed. SAP's standard duplicate check compares `XBLNR` exactly, so it misses these.

## How the KPIs are tested

`data_generator/generate_sap_p2p.py` writes `expected_metrics.json`, which computes every KPI above directly from the generated rows in plain Python, independently of Spark. Notebook 04 compares `gold_kpi_summary` against it: counts must match exactly, rates to 1e-9, and money to £0.005. On real SAP data, reconcile against standard reports instead: ME2N/ME80FN for PO values, MB5S for GR/IR balances, and FBL1H for open and cleared supplier items.
