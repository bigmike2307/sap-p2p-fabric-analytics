# SAP CDS extraction views

One extraction-enabled CDS view entity per landing file. Each view projects only the fields the pipeline needs, filters out irrelevant document types, and enables **automatic change data capture** so the extraction tool receives deltas instead of full reloads.

| View | Source table | Landing file | Notes |
|---|---|---|---|
| `ZX_P2P_EBAN` | EBAN | `EBAN.csv` | purchase requisition items |
| `ZX_P2P_EKKO` | EKKO | `EKKO.csv` | `BSTYP = 'F'`: purchase orders only |
| `ZX_P2P_EKPO` | EKPO | `EKPO.csv` | amounts cast to `DEC` (currency key is on EKKO) |
| `ZX_P2P_EKET` | EKET | `EKET.csv` | delivery dates and delivered quantities |
| `ZX_P2P_EKBE` | EKBE | `EKBE.csv` | goods receipts (`VGABE = '1'`) and invoice receipts (`VGABE = '2'`) |
| `ZX_P2P_RBKP` | RBKP | `RBKP.csv` | supplier invoice headers (MIRO) |
| `ZX_P2P_RSEG` | RSEG | `RSEG.csv` | supplier invoice items with PO and GR references |
| `ZX_P2P_BKPF` | BKPF | `BKPF.csv` | `AWTYP = 'RMRP'`: FI documents created by MIRO |
| `ZX_P2P_BSAK` | BSEG | `BSAK.csv` | cleared supplier items. In S/4HANA BSAK is a compatibility view, so this reads BSEG |

Master data (`LFA1`, `MARA`, `MAKT`, `T001W`, `T023T`, `T024`, `TCURR`) is small, so it is fully reloaded through the same pattern with `@Analytics.dataCategory: #DIMENSION`, or from released views such as `I_Supplier` and `I_Product`.

## Why table-grain views

- **CDC reliability.** Automatic change data capture tracks the underlying tables. Table-grain views keep the mapping between table rows and view rows simple.
- **Change without transports.** Joins and KPI rules live in the lakehouse, where they are versioned in Git and tested in CI. Changing a KPI does not need an ABAP transport.
- **Low SAP load.** The extraction does no joins or aggregation on the SAP application server.

## Why some fields are cast

CDS view entities require every amount and quantity to reference a currency or unit **within the same view**. Where that reference lives on another table (for example `EKPO-NETWR` → `EKKO-WAERS`), the field is cast to `abap.dec`, and silver pairs it with the right currency.

## Consuming the views

The views are exposed through ODP (context `ABAP_CDS`). Any ODP-capable tool can land them as files in the Lakehouse `Files/landing/sap_p2p` folder, for example SAP Datasphere replication flows, Azure Data Factory's SAP CDC connector, or a partner replication tool. Apply company-code and date selections in the ODP subscription rather than hard-coding them in the views. In this repository, `data_generator/` produces that landing folder.

## Before activating

These sources follow S/4HANA 2020+ view-entity syntax but have not been activated on a live system as part of this repository. Before using them on a real system:

1. Check them in ADT: field availability differs by release (for example `EBAN-WAERS`, and the `H_*` header fields on BSEG).
2. Check that automatic CDC supports each view on your release. Filters on the source table are supported; on older releases use classic DDIC-based views (`@AbapCatalog.sqlViewName`).
3. Add a DCL role if extraction users should be restricted by company code. The views currently use `#NOT_REQUIRED` because the extraction runs as a technical user.
