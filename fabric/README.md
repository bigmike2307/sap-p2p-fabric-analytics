# Running it in Microsoft Fabric

About an hour end to end on a Fabric trial capacity. Item names below are suggestions; keep them consistent so the pipeline and deployment rules line up.

## 1. Workspace and lakehouse

1. Create a workspace `P2P Analytics [DEV]` on your trial or F-SKU capacity.
2. Create a lakehouse `lh_p2p`.

## 2. Land the SAP extract

```bash
python data_generator/generate_sap_p2p.py --out output
```

In `lh_p2p` → **Files**, create `landing/sap_p2p` and upload everything in `output/`: 16 CSVs plus `manifest.json` and `expected_metrics.json`. With OneLake file explorer you can drag the folder in instead.

> In production this folder is filled by the ODP extraction of the `ZX_P2P_*` CDS views (see `sap_cds/README.md`). Nothing else changes.

## 3. Import and run the notebooks

1. Workspace → **Import** → **Notebook** → **From this computer**, and select the four files in `fabric/notebooks/`.
2. Open each notebook and attach `lh_p2p` as the **default lakehouse**.
3. Run them in order: 01 → 04. Notebook 04 should end with `54/54 checks passed`.

## 4. Orchestrate with a Data Pipeline

Create a pipeline `pl_p2p_daily`:

| Activity | Type | Runs after |
|---|---|---|
| Bronze | Notebook → `nb_01_bronze_ingest` | |
| Silver | Notebook → `nb_02_silver_conform` | Bronze **on success** |
| Gold | Notebook → `nb_03_gold_model` | Silver **on success** |
| Quality gate | Notebook → `nb_04_data_quality` | Gold **on success** |
| Refresh model | Semantic model refresh → `sm_p2p` | Quality gate **on success** |
| Alert | Teams or Outlook activity | any notebook **on failure** |

Pass `LANDING_PATH` (and `AS_OF_DATE` for back-dated reruns) as notebook **base parameters**; the first code cell of each notebook is tagged as the parameter cell. Schedule the pipeline daily, after the SAP extraction finishes.

## 5. Direct Lake semantic model

1. In `lh_p2p` → **New semantic model** `sm_p2p` → select the `gold_fact_*` and `gold_dim_*` tables.
2. Create the relationships shown in the main README's data model, mark `gold_dim_date` as the date table, and rename tables to friendly names (`'PO Item'`, `'Supplier Invoice'`, `'Supplier'`, `'Date'` …).
3. Add the measures from `powerbi/measures.dax`.
4. Build the report pages described in `powerbi/report_design.md`.

Fabric writes Delta tables with V-Order by default, which Direct Lake reads fastest. Run `OPTIMIZE` on the gold tables periodically once incremental loads are added.

## 6. Source control and deployment

- **Git integration:** connect the DEV workspace to this repository (folder `fabric/workspace/`). Fabric commits the notebooks, pipeline, semantic model and report in its own text formats.
- **Deployment pipeline:** DEV → TEST → PROD workspaces. Add deployment rules so each stage's notebooks bind to that stage's lakehouse, and promote only after the quality gate passes in TEST.
- **CI:** `.github/workflows/ci.yml` runs the full pipeline on local Spark for every push. A broken transformation fails the build before it reaches Fabric.

## Screenshots for the portfolio

Capture these and add them to `docs/images/`, then reference them from the main README:

1. Lakehouse explorer showing the bronze / silver / gold tables
2. Pipeline run view with all activities green
3. Notebook 04 output with all checks passed
4. Semantic model diagram view
5. Each report page
