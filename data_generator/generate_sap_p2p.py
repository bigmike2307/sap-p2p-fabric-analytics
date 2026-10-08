#!/usr/bin/env python3
"""
Synthetic SAP S/4HANA Procure-to-Pay data generator
====================================================

Writes CSV extracts shaped like the SAP MM / FI tables a P2P analytics
solution reads:

    master data   LFA1, MARA, MAKT, T001W, T024, TCURR
    texts         T023T
    requisitions  EBAN
    purchasing    EKKO, EKPO, EKET, EKBE
    invoicing     RBKP, RSEG
    payables      BKPF, BSAK

SAP conventions are kept on purpose, because handling them is part of the job:
YYYYMMDD dates with '00000000' for "empty", zero-padded keys (ALPHA format),
debit/credit indicators (SHKZG) instead of signed amounts, price units (PEINH),
inverted exchange-rate dates (TCURR-GDATU) and indirect quotations stored as
negative rates (TCURR-UKURS).

Known process problems are injected (late and short deliveries, after-the-fact
POs, invoice price/quantity variances, duplicate invoices, late and early
payments, goods-receipt reversals). The expected KPI values are computed from the
emitted rows and written to expected_metrics.json so the Fabric pipeline can be
tested end to end against an independent implementation.

Kestrel Foods, its suppliers and materials are fictional.

Usage:
    python generate_sap_p2p.py --out ./output
    python generate_sap_p2p.py --out ./output --seed 7 --scale 0.5
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import random
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Organisation
# ---------------------------------------------------------------------------
MANDT = "100"
COMPANY_CODE = "GB10"
PURCH_ORG = "GB10"
LOCAL_CURRENCY = "GBP"
PAYMENT_RUN_WEEKDAY = 3  # Thursday (F110 weekly run)

PLANTS = [
    ("1100", "Kestrel Foods Manchester", "Manchester", 0.45),
    ("1200", "Kestrel Foods Leeds", "Leeds", 0.40),
    ("1300", "Kestrel Foods Bristol DC", "Bristol", 0.15),
]

PURCHASING_GROUPS = {
    "100": ("Ingredients", ["BUYER01", "BUYER02"]),
    "110": ("Packaging", ["BUYER03"]),
    "120": ("MRO & Spares", ["BUYER04", "BUYER05"]),
    "130": ("Indirect & Services", ["BUYER06", "BUYER07"]),
}

# Each category maps to an SAP material group (MATKL). Prices are GBP per PEINH units.
CATEGORIES = {
    "ING-DRY": dict(
        ekgrp="100", mtart="ROH", uom="KG", step=25, peinh=1, price=(0.35, 3.2), qty=(500, 20000),
        lead=(7, 21), weight=0.22, pr_rate=0.94, atf_rate=0.015, knttp="", lgort="0001", tax="P0",
        variants=["25kg bag", "1t big bag"],
        names=["Wheat flour T55", "Wholemeal flour", "Caster sugar", "Granulated sugar", "Icing sugar",
               "Rolled oats", "Jumbo oat flakes", "Cocoa powder 10/12", "Corn starch", "Rice flour",
               "Dextrose", "Sea salt fine", "Baking powder", "Sodium bicarbonate", "Desiccated coconut",
               "Ground almonds", "Hazelnut pieces", "Sultanas", "Raisins", "Dried cranberries",
               "Chocolate chips 54%", "Glucose syrup solids", "Malt extract powder", "Sunflower seeds"]),
    "ING-DAIRY": dict(
        ekgrp="100", mtart="ROH", uom="KG", step=25, peinh=1, price=(1.8, 7.5), qty=(250, 8000),
        lead=(3, 10), weight=0.12, pr_rate=0.94, atf_rate=0.015, knttp="", lgort="0001", tax="P0",
        variants=["25kg", "bulk"],
        names=["Butter unsalted 82%", "Skimmed milk powder", "Whole milk powder", "Whey powder",
               "Cheddar mature", "Buttermilk powder", "Whole egg powder", "Cream powder 40%"]),
    "ING-FLAV": dict(
        ekgrp="100", mtart="ROH", uom="KG", step=5, peinh=1, price=(12, 95), qty=(25, 600),
        lead=(10, 35), weight=0.07, pr_rate=0.92, atf_rate=0.02, knttp="", lgort="0001", tax="P0",
        variants=[""],
        names=["Vanilla extract natural", "Caramel flavour", "Strawberry flavour", "Lemon oil",
               "Cinnamon ground", "Ginger ground", "Mixed spice", "Paprika extract colour",
               "Beetroot colour", "Citric acid", "Sunflower lecithin", "Peppermint oil"]),
    "PKG-FILM": dict(
        ekgrp="110", mtart="VERP", uom="M", step=500, peinh=1000, price=(35, 260), qty=(5000, 120000),
        lead=(14, 35), weight=0.09, pr_rate=0.93, atf_rate=0.015, knttp="", lgort="0002", tax="P1",
        variants=[""],
        names=["Flow wrap film 300mm", "Flow wrap film 420mm", "Metallised OPP film 350mm",
               "Stretch wrap 500mm", "Shrink film 600mm", "Lidding film 180mm", "Paper wrap 280mm"]),
    "PKG-CART": dict(
        ekgrp="110", mtart="VERP", uom="EA", step=500, peinh=1000, price=(70, 650), qty=(2000, 80000),
        lead=(10, 28), weight=0.12, pr_rate=0.93, atf_rate=0.015, knttp="", lgort="0002", tax="P1",
        variants=[""],
        names=["Shipper case 12x200g", "Shipper case 24x45g", "Retail carton 400g", "Retail carton 250g",
               "Display tray 18x", "Pallet layer pad", "Corner board 1m", "Thermal label 100x150"]),
    "MRO-SPARE": dict(
        ekgrp="120", mtart="ERSA", uom="EA", step=1, peinh=1, price=(18, 2400), qty=(1, 12),
        lead=(3, 30), weight=0.12, pr_rate=0.85, atf_rate=0.05, knttp="", lgort="0003", tax="P1",
        variants=[""],
        names=["Bearing 6205-2RS", "Gearbox motor 0.75kW", "Conveyor belt 600mm", "Sealing jaw assembly",
               "Proximity sensor M18", "Servo drive 2kW", "Pneumatic cylinder 50x100", "Timing belt HTD 8M",
               "Load cell 50kg", "Heater cartridge 400W", "Inverter drive 5.5kW", "Date coder printhead"]),
    "MRO-CONS": dict(
        ekgrp="120", mtart="HIBE", uom="EA", step=10, peinh=1, price=(1.5, 65), qty=(10, 400),
        lead=(2, 10), weight=0.10, pr_rate=0.80, atf_rate=0.06, knttp="K", lgort="", tax="P1",
        variants=[""],
        names=["Nitrile gloves blue L", "Hairnets white", "Food-grade lubricant 400ml", "Detergent 20L",
               "Sanitiser spray 5L", "Blue roll 2-ply", "Cable ties 300mm", "Ear plugs", "Hi-vis vest",
               "Detectable plasters"]),
    "SRV-FM": dict(
        ekgrp="130", service=True, uom="AU", step=1, peinh=1, price=(250, 9500), qty=(1, 1),
        lead=(5, 30), weight=0.09, pr_rate=0.70, atf_rate=0.14, knttp="K", lgort="", tax="P1",
        names=["Pest control service", "Waste management", "Site cleaning contract",
               "Fire system maintenance", "Forklift maintenance", "HVAC maintenance", "Security guarding"]),
    "SRV-PROF": dict(
        ekgrp="130", service=True, uom="AU", step=1, peinh=1, price=(1200, 24000), qty=(1, 1),
        lead=(10, 45), weight=0.07, pr_rate=0.60, atf_rate=0.16, knttp="K", lgort="", tax="P1",
        names=["Food safety audit", "IT support services", "Engineering consultancy", "Recruitment fees",
               "Legal advisory", "BRCGS training"]),
}

MATERIAL_GROUP_TEXTS = {
    "ING-DRY": "Dry ingredients", "ING-DAIRY": "Dairy ingredients", "ING-FLAV": "Flavours & colours",
    "PKG-FILM": "Flexible packaging", "PKG-CART": "Cartons & cases", "MRO-SPARE": "MRO spare parts",
    "MRO-CONS": "MRO consumables", "SRV-FM": "Facilities services", "SRV-PROF": "Prof. services",
}

SUPPLIERS_PER_CATEGORY = {
    "ING-DRY": 14, "ING-DAIRY": 8, "ING-FLAV": 8, "PKG-FILM": 7, "PKG-CART": 9,
    "MRO-SPARE": 12, "MRO-CONS": 8, "SRV-FM": 12, "SRV-PROF": 14,
}

COUNTRY_MIX = {
    "ING-DRY": [("GB", 0.70), ("IE", 0.10), ("NL", 0.10), ("DE", 0.10)],
    "ING-DAIRY": [("GB", 0.75), ("IE", 0.25)],
    "ING-FLAV": [("GB", 0.40), ("DE", 0.20), ("FR", 0.20), ("NL", 0.10), ("US", 0.10)],
    "PKG-FILM": [("GB", 0.50), ("DE", 0.25), ("NL", 0.15), ("CN", 0.10)],
    "PKG-CART": [("GB", 0.85), ("IE", 0.15)],
    "MRO-SPARE": [("GB", 0.60), ("DE", 0.25), ("US", 0.15)],
    "MRO-CONS": [("GB", 0.90), ("NL", 0.10)],
    "SRV-FM": [("GB", 1.00)],
    "SRV-PROF": [("GB", 1.00)],
}

COUNTRIES = {
    "GB": ("GBP", "Ltd", ["Manchester", "Leeds", "Birmingham", "Bristol", "Glasgow", "Sheffield",
                         "Nottingham", "Liverpool", "Hull", "Leicester"]),
    "IE": ("EUR", "Ltd", ["Dublin", "Cork", "Limerick"]),
    "NL": ("EUR", "B.V.", ["Rotterdam", "Utrecht", "Eindhoven"]),
    "DE": ("EUR", "GmbH", ["Hamburg", "Cologne", "Munich", "Bremen"]),
    "FR": ("EUR", "SAS", ["Lyon", "Lille", "Nantes"]),
    "US": ("USD", "Inc.", ["Chicago", "Atlanta", "Columbus"]),
    "CN": ("USD", "Co., Ltd.", ["Ningbo", "Shenzhen", "Suzhou"]),
}

NAME_PREFIXES = [
    "Albion", "Pennine", "Severn", "Northgate", "Brightwater", "Harbourside", "Meridian", "Oakfield",
    "Thameside", "Cotswold", "Highmoor", "Riverside", "Kingsway", "Fenland", "Weald", "Clydebank",
    "Mersey", "Tynedale", "Wessex", "Ashdown", "Blackwood", "Greystone", "Holloway", "Larkspur",
    "Marlow", "Netherby", "Orchard", "Redbrook", "Stonebridge", "Westfield", "Calder", "Dunmore",
    "Elmstead", "Foxley", "Glenmoor", "Hartwell", "Ivybridge", "Juniper", "Kestwick", "Linden",
]
NAME_SUFFIXES = {
    "ING-DRY": ["Ingredients", "Milling", "Foods"],
    "ING-DAIRY": ["Dairies", "Dairy Ingredients"],
    "ING-FLAV": ["Flavours", "Spice Co"],
    "PKG-FILM": ["Films", "Flexibles"],
    "PKG-CART": ["Packaging", "Corrugated"],
    "MRO-SPARE": ["Engineering", "Automation", "Bearings"],
    "MRO-CONS": ["Industrial Supplies", "Hygiene Supplies"],
    "SRV-FM": ["Facilities", "Site Services"],
    "SRV-PROF": ["Consulting", "Advisory", "Solutions"],
}

# Supplier performance tiers: (weight, on-time prob, in-full prob, invoice price-variance prob)
SUPPLIER_TIERS = [(0.40, 0.95, 0.97, 0.02), (0.45, 0.85, 0.90, 0.05), (0.15, 0.62, 0.75, 0.12)]
PAYMENT_TERMS = [("0030", 0.55), ("0060", 0.20), ("0045", 0.15), ("0014", 0.10)]

CENT = Decimal("0.01")
MILLI = Decimal("0.001")
RATE_Q = Decimal("0.000001")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def money(x) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def qty3(x) -> Decimal:
    return Decimal(x).quantize(MILLI, rounding=ROUND_HALF_UP)


def sap_date(d: date | None) -> str:
    return d.strftime("%Y%m%d") if d else "00000000"


def parse_sap_date(s: str) -> date | None:
    return None if s in ("", "00000000") else datetime.strptime(s, "%Y%m%d").date()


def effective_rate(ukurs: str) -> Decimal:
    """TCURR-UKURS: positive = direct quotation, negative = indirect quotation."""
    value = Decimal(ukurs)
    rate = Decimal(1) / abs(value) if value < 0 else value
    return rate.quantize(RATE_Q, rounding=ROUND_HALF_UP)


def weighted(rng: random.Random, pairs):
    values, weights = zip(*pairs)
    return rng.choices(values, weights=weights, k=1)[0]


def log_uniform(rng: random.Random, lo: float, hi: float) -> float:
    return lo * (hi / lo) ** rng.random() if hi > lo else lo


def round_to_step(x: float, step: int) -> Decimal:
    return qty3(max(step, round(x / step) * step))


def next_weekday(d: date, weekday: int) -> date:
    return d + timedelta(days=(weekday - d.weekday()) % 7)


def prev_weekday(d: date, weekday: int) -> date:
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def normalise_reference(xblnr: str) -> str:
    """Supplier invoice reference normalised for duplicate detection."""
    digits = re.sub(r"[^0-9]", "", xblnr)
    if digits:
        return digits.lstrip("0")
    return re.sub(r"[^A-Za-z0-9]", "", xblnr).upper()


class YearlyNumberRange:
    """SAP-style document number ranges that restart every fiscal year."""

    def __init__(self, base: int):
        self.base = base
        self.counters: dict[int, int] = defaultdict(int)

    def next(self, year: int) -> str:
        self.counters[year] += 1
        return f"{self.base + self.counters[year]:010d}"


class FxRates:
    """Monthly 'M' rates to GBP, stored the way TCURR stores them."""

    def __init__(self, rng: random.Random, first: date, last: date):
        self.rows: list[dict] = []
        self.valid: dict[str, list[tuple[date, Decimal]]] = {"EUR": [], "USD": []}
        eur, usd = 0.855, 0.775
        d = date(first.year, first.month, 1)
        while d <= last:
            eur *= 1 + rng.gauss(0, 0.008)
            usd *= 1 + rng.gauss(0, 0.012)
            # EUR stored as an indirect quotation (negative), USD as a direct quotation.
            quotes = {"EUR": f"-{Decimal(1 / eur).quantize(Decimal('0.00001'))}",
                      "USD": f"{Decimal(usd).quantize(Decimal('0.00001'))}"}
            for fcurr, ukurs in quotes.items():
                self.rows.append({
                    "KURST": "M", "FCURR": fcurr, "TCURR": LOCAL_CURRENCY,
                    "GDATU": str(99999999 - int(sap_date(d))), "UKURS": ukurs, "FFACT": "1", "TFACT": "1",
                })
                self.valid[fcurr].append((d, effective_rate(ukurs)))
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)

    def rate(self, currency: str, on: date) -> Decimal:
        if currency == LOCAL_CURRENCY:
            return Decimal(1)
        series = self.valid[currency]
        idx = bisect.bisect_right([v for v, _ in series], on) - 1
        return series[max(idx, 0)][1]


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
def build_materials(rng: random.Random, start: date) -> dict[str, list[dict]]:
    by_category: dict[str, list[dict]] = defaultdict(list)
    counters = {"ROH": 10000000, "VERP": 20000000, "ERSA": 30000000, "HIBE": 40000000}
    for matkl, cat in CATEGORIES.items():
        if cat.get("service"):
            continue
        for name in cat["names"]:
            variants = cat["variants"]
            for variant in rng.sample(variants, k=rng.randint(1, len(variants))):
                counters[cat["mtart"]] += 1
                lo, hi = cat["price"]
                by_category[matkl].append({
                    "matnr": f"{counters[cat['mtart']]:018d}",
                    "matkl": matkl,
                    "mtart": cat["mtart"],
                    "meins": cat["uom"],
                    "maktx": f"{name} {variant}".strip()[:40],
                    "base_price": round(log_uniform(rng, lo, hi), 2),
                    "ersda": start - timedelta(days=rng.randint(200, 3000)),
                })
    return by_category


def build_suppliers(rng: random.Random, start: date, end: date) -> dict[str, list[dict]]:
    by_category: dict[str, list[dict]] = defaultdict(list)
    used_names: set[str] = set()
    number = 100000
    for matkl, count in SUPPLIERS_PER_CATEGORY.items():
        prefixes = rng.sample(NAME_PREFIXES, k=count)
        for rank, prefix in enumerate(prefixes, start=1):
            number += 1
            country = weighted(rng, COUNTRY_MIX[matkl])
            currency, legal, cities = COUNTRIES[country]
            name = f"{prefix} {rng.choice(NAME_SUFFIXES[matkl])} {legal}"
            while name in used_names:
                name = f"{prefix} {rng.choice(NAME_SUFFIXES[matkl])} {rng.randint(2, 9)} {legal}"
            used_names.add(name)
            _, on_time, in_full, price_var = weighted(rng, [(t, t[0]) for t in SUPPLIER_TIERS])
            ref_style = rng.choice(["INV-{n:06d}", "{n:08d}", "SI{n}", "{p}/{yy}/{n:05d}"])
            by_category[matkl].append({
                "lifnr": f"{number:010d}",
                "name": name[:35],
                "country": country,
                "city": rng.choice(cities),
                "currency": currency,
                "volume_weight": 1 / rank ** 0.9,  # Pareto-like spend concentration
                "on_time": on_time,
                "in_full": in_full,
                "price_var": price_var,
                "zterm": weighted(rng, PAYMENT_TERMS) if not matkl.startswith("SRV") else rng.choice(["0014", "0030"]),
                "ref_style": ref_style,
                "ref_prefix": "".join(w[0] for w in name.split()[:2]).upper(),
                "ref_counter": rng.randint(1000, 60000),
                "erdat": start - timedelta(days=rng.randint(100, 3000)),
                "blocked_from": None,
            })
    # Two suppliers were blocked for purchasing part-way through the period.
    all_suppliers = [s for group in by_category.values() for s in group]
    for s in rng.sample(all_suppliers, k=2):
        s["blocked_from"] = start + timedelta(days=rng.randint(365, (end - start).days - 30))
    return by_category


def next_invoice_reference(supplier: dict, invoice_date: date) -> str:
    supplier["ref_counter"] += 1
    return supplier["ref_style"].format(
        n=supplier["ref_counter"], p=supplier["ref_prefix"], yy=f"{invoice_date:%y}")


def duplicate_reference_variant(rng: random.Random, xblnr: str) -> str:
    """How a resubmitted invoice tends to be keyed in: same number, different formatting."""
    digits = re.sub(r"[^0-9]", "", xblnr)
    letters = re.sub(r"[^A-Za-z]", "", xblnr)
    options = [
        f"{letters}{digits.lstrip('0')}",
        digits.lstrip("0") or digits,
        f"{letters.lower()}-{digits}" if letters else f"{digits} ",
        f"{letters} {digits}".strip(),
    ]
    options = [o.strip() for o in options if o.strip() and o.strip() != xblnr]
    return rng.choice(options) if options else f"{xblnr}-DUP"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------
class P2PGenerator:
    def __init__(self, seed: int, scale: float, start: date, end: date, as_of: date):
        self.rng = random.Random(seed)
        self.scale, self.start, self.end, self.as_of = scale, start, end, as_of
        self.fx = FxRates(self.rng, start - timedelta(days=31), as_of)
        self.materials = build_materials(self.rng, start)
        self.suppliers = build_suppliers(self.rng, start, end)
        self.t: dict[str, list[dict]] = defaultdict(list)
        self.po_numbers = iter(range(4500000001, 4599999999))
        self.pr_numbers = iter(range(10000001, 19999999))
        self.mat_docs = YearlyNumberRange(5000000000)
        self.inv_docs = YearlyNumberRange(5105600000)
        self.fi_docs = YearlyNumberRange(1900000000)
        self.pay_docs = YearlyNumberRange(1500000000)

    # -- master data --------------------------------------------------------
    def emit_master_data(self):
        for werks, name, city, _ in PLANTS:
            self.t["T001W"].append({"WERKS": werks, "NAME1": name, "ORT01": city,
                                    "LAND1": "GB", "BWKEY": werks})
        for matkl, wgbez in MATERIAL_GROUP_TEXTS.items():
            self.t["T023T"].append({"SPRAS": "E", "MATKL": matkl, "WGBEZ": wgbez})
        for ekgrp, (eknam, _) in PURCHASING_GROUPS.items():
            self.t["T024"].append({"EKGRP": ekgrp, "EKNAM": eknam})
        for group in self.materials.values():
            for m in group:
                self.t["MARA"].append({"MATNR": m["matnr"], "MTART": m["mtart"],
                                       "MATKL": m["matkl"], "MEINS": m["meins"],
                                       "ERSDA": sap_date(m["ersda"]), "LVORM": ""})
                self.t["MAKT"].append({"MATNR": m["matnr"], "SPRAS": "E",
                                       "MAKTX": m["maktx"]})
        for group in self.suppliers.values():
            for s in group:
                self.t["LFA1"].append({"LIFNR": s["lifnr"], "NAME1": s["name"],
                                       "LAND1": s["country"], "ORT01": s["city"], "KTOKK": "LIEF",
                                       "SPERR": "X" if s["blocked_from"] else "", "LOEVM": "",
                                       "ERDAT": sap_date(s["erdat"])})
        self.t["TCURR"] = self.fx.rows

    # -- transactional data -------------------------------------------------
    def run(self):
        self.emit_master_data()
        day = self.start
        while day <= self.end:
            if day.weekday() < 5:
                season = 1.2 if day.month in (9, 10, 11) else 0.85 if day.month in (12, 1) else 1.0
                mean = 7 * self.scale * season
                for _ in range(max(0, round(self.rng.gauss(mean, math.sqrt(mean))))):
                    self.create_purchase_order(day)
                if self.rng.random() < 0.15 * self.scale:
                    self.create_unconverted_requisition(day)
            day += timedelta(days=1)
        return self.t

    def pick_supplier(self, matkl: str, po_date: date) -> dict:
        candidates = [s for s in self.suppliers[matkl]
                      if not (s["blocked_from"] and po_date >= s["blocked_from"])]
        return self.rng.choices(candidates, weights=[s["volume_weight"] for s in candidates], k=1)[0]

    def create_unconverted_requisition(self, day: date):
        matkl = weighted(self.rng, [(k, v["weight"]) for k, v in CATEGORIES.items() if not v.get("service")])
        cat = CATEGORIES[matkl]
        material = self.rng.choice(self.materials[matkl])
        age = (self.as_of - day).days
        released = age > 10 or self.rng.random() < 0.5
        deleted = age > 60 and self.rng.random() < 0.5
        self.t["EBAN"].append({
            "BANFN": f"{next(self.pr_numbers):010d}", "BNFPO": "00010", "BSART": "NB",
            "LOEKZ": "X" if deleted else "", "STATU": "N", "EKGRP": cat["ekgrp"],
            "AFNAM": f"PLANT{self.rng.randint(1, 9):02d}", "TXZ01": material["maktx"],
            "MATNR": material["matnr"], "WERKS": weighted(self.rng, [(p[0], p[3]) for p in PLANTS]),
            "MATKL": matkl, "MENGE": f"{round_to_step(log_uniform(self.rng, *cat['qty']), cat['step'])}",
            "MEINS": cat["uom"], "BADAT": sap_date(day),
            "FRGDT": sap_date(day + timedelta(days=self.rng.randint(0, 2)) if released else None),
            "LFDAT": sap_date(day + timedelta(days=self.rng.randint(*cat["lead"]))),
            "PREIS": f"{money(material['base_price'])}", "PEINH": str(cat["peinh"]), "WAERS": LOCAL_CURRENCY,
            "KNTTP": cat["knttp"], "EBELN": "", "EBELP": "00000",
        })

    def create_purchase_order(self, po_date: date):
        rng = self.rng
        matkl = weighted(rng, [(k, v["weight"]) for k, v in CATEGORIES.items()])
        cat = CATEGORIES[matkl]
        supplier = self.pick_supplier(matkl, po_date)
        currency = supplier["currency"]
        rate = self.fx.rate(currency, po_date)
        ebeln = f"{next(self.po_numbers):010d}"
        plant = weighted(rng, [(p[0], p[3]) for p in PLANTS])
        is_service = cat.get("service", False)

        after_the_fact = rng.random() < cat["atf_rate"]
        pr_backed = rng.random() < (0.3 if after_the_fact else cat["pr_rate"])
        atf_invoice_date = po_date - timedelta(days=rng.randint(3, 25)) if after_the_fact else None

        banfn = f"{next(self.pr_numbers):010d}" if pr_backed else ""
        if pr_backed:
            if after_the_fact:  # retrospective requisition raised the same day
                badat = frgdt = po_date - timedelta(days=rng.randint(0, 1))
            else:
                max_cycle = {"100": 6, "110": 6, "120": 10, "130": 25}[cat["ekgrp"]]
                badat = po_date - timedelta(days=rng.randint(1, max_cycle))
                frgdt = min(badat + timedelta(days=rng.randint(0, 2)), po_date)

        self.t["EKKO"].append({
            "EBELN": ebeln, "BUKRS": COMPANY_CODE, "BSTYP": "F", "BSART": "NB",
            "LIFNR": supplier["lifnr"], "EKORG": PURCH_ORG, "EKGRP": cat["ekgrp"], "WAERS": currency,
            "BEDAT": sap_date(po_date), "AEDAT": sap_date(po_date),
            "ERNAM": rng.choice(PURCHASING_GROUPS[cat["ekgrp"]][1]), "ZTERM": supplier["zterm"], "FRGKE": "R",
        })

        if is_service:
            lines = [None]
        else:
            n_items = min(rng.choice([1, 1, 2, 2, 3, 4, 5, 6]), len(self.materials[matkl]))
            lines = rng.sample(self.materials[matkl], k=n_items)

        gr_events = []  # (item, gr_doc, gr_year, gr_date, gr_qty, gr_dmbtr, unit_price_doc)
        years_in = (po_date - self.start).days / 365
        for idx, material in enumerate(lines, start=1):
            ebelp = f"{idx * 10:05d}"
            if is_service:
                txz01 = f"{rng.choice(cat['names'])} {po_date:%b-%y}"
                price_gbp = log_uniform(rng, *cat["price"])
                qty = Decimal("1.000")
                matnr = ""
            else:
                txz01 = material["maktx"]
                price_gbp = material["base_price"] * (1 + 0.035 * years_in) * (1 + rng.gauss(0, 0.02))
                qty = round_to_step(log_uniform(rng, *cat["qty"]), cat["step"])
                matnr = material["matnr"]
            netpr = money(Decimal(str(price_gbp)) / rate)
            peinh = Decimal(cat["peinh"])
            netwr = money(qty * netpr / peinh)
            deleted = rng.random() < 0.015
            eindt = po_date if after_the_fact else po_date + timedelta(days=rng.randint(*cat["lead"]))

            item = {"ebeln": ebeln, "ebelp": ebelp, "matnr": matnr, "plant": plant, "qty": qty,
                    "netpr": netpr, "peinh": peinh, "currency": currency, "supplier": supplier,
                    "cat": cat, "after_the_fact": after_the_fact, "atf_invoice_date": atf_invoice_date,
                    "po_date": po_date, "zterm": supplier["zterm"]}

            gr_total = Decimal(0)
            short_closed = False
            if not deleted:
                gr_total, short_closed = self.simulate_goods_receipts(item, eindt, gr_events)

            if pr_backed:
                self.t["EBAN"].append({
                    "BANFN": banfn, "BNFPO": ebelp, "BSART": "NB", "LOEKZ": "",
                    "STATU": "B", "EKGRP": cat["ekgrp"], "AFNAM": f"PLANT{rng.randint(1, 9):02d}",
                    "TXZ01": txz01, "MATNR": matnr, "WERKS": plant, "MATKL": matkl, "MENGE": f"{qty}",
                    "MEINS": cat["uom"], "BADAT": sap_date(badat), "FRGDT": sap_date(frgdt),
                    "LFDAT": sap_date(eindt), "PREIS": f"{money(Decimal(str(price_gbp)))}",
                    "PEINH": str(cat["peinh"]), "WAERS": LOCAL_CURRENCY, "KNTTP": cat["knttp"],
                    "EBELN": ebeln, "EBELP": ebelp,
                })
            self.t["EKPO"].append({
                "EBELN": ebeln, "EBELP": ebelp, "LOEKZ": "L" if deleted else "",
                "TXZ01": txz01[:40], "MATNR": matnr, "WERKS": plant, "LGORT": cat["lgort"], "MATKL": matkl,
                "MENGE": f"{qty}", "MEINS": cat["uom"], "NETPR": f"{netpr}", "PEINH": str(cat["peinh"]),
                "NETWR": f"{netwr}", "MWSKZ": cat["tax"], "KNTTP": cat["knttp"],
                "ELIKZ": "X" if (short_closed or gr_total >= qty * Decimal("0.98")) else "",
                "EREKZ": "", "WEPOS": "X", "REPOS": "X", "WEBRE": "X",
                "BANFN": banfn, "BNFPO": ebelp if pr_backed else "00000", "AEDAT": sap_date(po_date),
            })
            self.t["EKET"].append({
                "EBELN": ebeln, "EBELP": ebelp, "ETENR": "0001", "EINDT": sap_date(eindt),
                "SLFDT": sap_date(eindt), "MENGE": f"{qty}", "WEMNG": f"{qty3(gr_total)}",
            })

        self.create_invoices(ebeln, supplier, currency, gr_events, after_the_fact, atf_invoice_date)

    def post_goods_movement(self, item: dict, budat: date, qty: Decimal, bwart: str) -> tuple[str, int, Decimal]:
        year = budat.year
        belnr = self.mat_docs.next(year)
        wrbtr = money(qty * item["netpr"] / item["peinh"])
        dmbtr = money(wrbtr * self.fx.rate(item["currency"], budat))
        self.t["EKBE"].append({
            "EBELN": item["ebeln"], "EBELP": item["ebelp"], "ZEKKN": "00", "VGABE": "1",
            "GJAHR": str(year), "BELNR": belnr, "BUZEI": "0001", "BEWTP": "E", "BWART": bwart,
            "BUDAT": sap_date(budat), "MENGE": f"{qty3(qty)}", "DMBTR": f"{dmbtr}", "WRBTR": f"{wrbtr}",
            "WAERS": item["currency"], "HSWAE": LOCAL_CURRENCY, "AREWR": f"{dmbtr}",
            "SHKZG": "S" if bwart == "101" else "H", "LFGJA": str(year), "LFBNR": belnr, "LFPOS": "0001",
            "CPUDT": sap_date(budat), "ERNAM": "WHSE01",
        })
        return belnr, year, dmbtr

    def simulate_goods_receipts(self, item: dict, eindt: date, gr_events: list) -> tuple[Decimal, bool]:
        rng, supplier, cat, qty = self.rng, item["supplier"], item["cat"], item["qty"]
        po_date = item["po_date"]
        if item["after_the_fact"]:
            first_date = po_date + timedelta(days=rng.randint(0, 3))  # retrospective GR
        elif rng.random() < supplier["on_time"]:
            first_date = eindt + timedelta(days=rng.randint(-3, 2))
        else:
            first_date = eindt + timedelta(days=rng.randint(3, 20))
        first_date = max(first_date, po_date + timedelta(days=1 if not item["after_the_fact"] else 0))

        deliveries: list[tuple[date, Decimal]] = []
        short_closed = False
        if cat.get("service") or item["after_the_fact"] or rng.random() < supplier["in_full"]:
            delivered = qty
            if cat["uom"] in ("KG", "M") and rng.random() < 0.04 and cat["step"] / float(qty) <= 0.05:
                delivered = qty + cat["step"]  # small over-delivery inside tolerance
            deliveries.append((first_date, delivered))
        else:
            first_qty = round_to_step(float(qty) * rng.uniform(0.5, 0.92), cat["step"])
            if first_qty >= qty:
                first_qty = qty - cat["step"] if qty > cat["step"] else qty
            deliveries.append((first_date, first_qty))
            if first_qty < qty:
                if rng.random() < 0.7:
                    deliveries.append((first_date + timedelta(days=rng.randint(4, 25)), qty - first_qty))
                else:
                    short_closed = True

        total = Decimal(0)
        for gr_date, gr_qty in deliveries:
            if gr_date > self.as_of:
                break
            if rng.random() < 0.012:  # wrong quantity booked, reversed (102) and re-posted
                self.post_goods_movement(item, gr_date, gr_qty, "101")
                self.post_goods_movement(item, gr_date + timedelta(days=1), gr_qty, "102")
                gr_date = gr_date + timedelta(days=rng.randint(1, 2))
                if gr_date > self.as_of:
                    break
            belnr, year, dmbtr = self.post_goods_movement(item, gr_date, gr_qty, "101")
            gr_events.append((item, belnr, year, gr_date, gr_qty, dmbtr))
            total += gr_qty
        return total, short_closed

    def create_invoices(self, ebeln, supplier, currency, gr_events, after_the_fact, atf_invoice_date):
        rng = self.rng
        by_date: dict[date, list] = defaultdict(list)
        for ev in gr_events:
            by_date[ev[3]].append(ev)
        for gr_date in sorted(by_date):
            events = by_date[gr_date]
            bldat = atf_invoice_date if after_the_fact else gr_date + timedelta(days=rng.randint(0, 4))
            budat = max(bldat + timedelta(days=rng.randint(1, 10)), gr_date + timedelta(days=rng.randint(0, 3)))
            if budat > self.as_of:
                continue
            if not after_the_fact and rng.random() < 0.012:
                continue  # invoice never arrives: the receipt sits on GR/IR and ages
            lines, blocked = [], False
            price_issue = rng.random() < supplier["price_var"]
            for item, gr_doc, gr_year, _, gr_qty, gr_dmbtr in events:
                unit_price = item["netpr"] / item["peinh"]
                if price_issue:
                    unit_price *= Decimal(str(rng.uniform(1.025, 1.12)))
                    blocked = True
                elif rng.random() < 0.05:
                    unit_price *= Decimal(str(rng.uniform(1.001, 1.015)))  # within 2% tolerance
                inv_qty = gr_qty
                if rng.random() < 0.012:
                    inv_qty = round_to_step(float(gr_qty) * rng.uniform(1.03, 1.10), item["cat"]["step"])
                    if inv_qty <= gr_qty:
                        inv_qty = gr_qty + item["cat"]["step"]
                    blocked = True
                amount = money(inv_qty * unit_price)
                arewr = gr_dmbtr if inv_qty == gr_qty else money(inv_qty * gr_dmbtr / gr_qty)
                lines.append((item, gr_doc, gr_year, inv_qty, amount, arewr))
            xblnr = next_invoice_reference(supplier, bldat)
            self.post_invoice(supplier, currency, lines, bldat, budat, xblnr, "R" if blocked else "")

            if not after_the_fact and rng.random() < 0.006:  # same invoice keyed in again later
                dup_budat = budat + timedelta(days=rng.randint(5, 60))
                if dup_budat <= self.as_of:
                    self.post_invoice(supplier, currency, lines, bldat, dup_budat,
                                      duplicate_reference_variant(rng, xblnr),
                                      "R" if rng.random() < 0.5 else "")

    def post_invoice(self, supplier, currency, lines, bldat, budat, xblnr, zlspr):
        rng = self.rng
        year = budat.year
        belnr = self.inv_docs.next(year)
        net = sum((amount for *_, amount, _ in lines), Decimal(0))
        tax_code = lines[0][0]["cat"]["tax"]
        tax = money(net * Decimal("0.20")) if tax_code == "P1" else Decimal("0.00")
        gross = net + tax
        zterm = supplier["zterm"]
        zbd1t = int(zterm)
        rate = self.fx.rate(currency, budat)

        self.t["RBKP"].append({
            "BELNR": belnr, "GJAHR": str(year), "BLART": "RE", "BLDAT": sap_date(bldat),
            "BUDAT": sap_date(budat), "USNAM": f"APCLERK{rng.randint(1, 4)}", "CPUDT": sap_date(budat),
            "XBLNR": xblnr, "BUKRS": COMPANY_CODE, "LIFNR": supplier["lifnr"], "WAERS": currency,
            "RMWWR": f"{gross}", "WMWST1": f"{tax}", "MWSKZ1": tax_code, "ZTERM": zterm, "ZBD1T": str(zbd1t),
            "ZFBDT": sap_date(bldat), "ZLSPR": zlspr, "RBSTAT": "5",
        })
        for pos, (item, gr_doc, gr_year, inv_qty, amount, arewr) in enumerate(lines, start=1):
            self.t["RSEG"].append({
                "BELNR": belnr, "GJAHR": str(year), "BUZEI": f"{pos:06d}",
                "EBELN": item["ebeln"], "EBELP": item["ebelp"], "MATNR": item["matnr"], "WERKS": item["plant"],
                "WRBTR": f"{amount}", "SHKZG": "S", "MWSKZ": tax_code, "MENGE": f"{qty3(inv_qty)}",
                "BSTME": item["cat"]["uom"], "LFBNR": gr_doc, "LFGJA": str(gr_year), "LFPOS": "0001",
            })
            self.t["EKBE"].append({
                "EBELN": item["ebeln"], "EBELP": item["ebelp"], "ZEKKN": "00", "VGABE": "2",
                "GJAHR": str(year), "BELNR": belnr, "BUZEI": f"{pos:04d}", "BEWTP": "Q", "BWART": "",
                "BUDAT": sap_date(budat), "MENGE": f"{qty3(inv_qty)}", "DMBTR": f"{money(amount * rate)}",
                "WRBTR": f"{amount}", "WAERS": currency, "HSWAE": LOCAL_CURRENCY, "AREWR": f"{arewr}",
                "SHKZG": "S", "LFGJA": str(gr_year), "LFBNR": gr_doc, "LFPOS": "0001",
                "CPUDT": sap_date(budat), "ERNAM": "APCLERK",
            })

        fi_belnr = self.fi_docs.next(year)
        self.t["BKPF"].append({
            "BUKRS": COMPANY_CODE, "BELNR": fi_belnr, "GJAHR": str(year), "BLART": "RE",
            "BLDAT": sap_date(bldat), "BUDAT": sap_date(budat), "AWTYP": "RMRP", "AWKEY": f"{belnr}{year}",
            "XBLNR": xblnr, "WAERS": currency, "USNAM": "APCLERK",
        })

        # Payment: weekly run; most invoices paid in the last run before the due date.
        due = bldat + timedelta(days=zbd1t)
        behaviour = weighted(rng, [("early", 0.08), ("late", 0.17), ("on_time", 0.75)])
        if behaviour == "early":
            augdt = next_weekday(budat + timedelta(days=1), PAYMENT_RUN_WEEKDAY)
        elif behaviour == "late":
            augdt = next_weekday(due + timedelta(days=rng.randint(3, 35)), PAYMENT_RUN_WEEKDAY)
        else:
            augdt = prev_weekday(due, PAYMENT_RUN_WEEKDAY)
            if augdt <= budat:
                augdt = next_weekday(budat + timedelta(days=1), PAYMENT_RUN_WEEKDAY)
        if zlspr:
            released = budat + timedelta(days=rng.randint(5, 40))
            augdt = max(augdt, next_weekday(released, PAYMENT_RUN_WEEKDAY))
        if augdt <= self.as_of:
            self.t["BSAK"].append({
                "BUKRS": COMPANY_CODE, "LIFNR": supplier["lifnr"], "AUGDT": sap_date(augdt),
                "AUGBL": self.pay_docs.next(augdt.year), "GJAHR": str(year), "BELNR": fi_belnr, "BUZEI": "001",
                "BUDAT": sap_date(budat), "BLDAT": sap_date(bldat), "WAERS": currency,
                "BLART": "RE", "SHKZG": "H", "DMBTR": f"{money(gross * rate)}", "WRBTR": f"{gross}",
                "ZFBDT": sap_date(bldat), "ZTERM": zterm, "ZBD1T": str(zbd1t),
            })


# ---------------------------------------------------------------------------
# Expected metrics: an independent, row-based implementation of the KPI rules
# that the gold layer must reproduce.
# ---------------------------------------------------------------------------
KPI_RULES = {
    "otif_tolerance_days": 2,
    "in_full_threshold": 0.98,
    "duplicate_window_days": 90,
    "early_payment_days": 7,
    "grir_aging_threshold_days": 90,
}


def compute_expected_metrics(t: dict[str, list[dict]], as_of: date) -> dict:
    tol = timedelta(days=KPI_RULES["otif_tolerance_days"])
    in_full = Decimal(str(KPI_RULES["in_full_threshold"]))

    fx: dict[str, list[tuple[date, Decimal]]] = defaultdict(list)
    for r in t["TCURR"]:
        valid_from = datetime.strptime(str(99999999 - int(r["GDATU"])), "%Y%m%d").date()
        fx[r["FCURR"]].append((valid_from, effective_rate(r["UKURS"])))
    for series in fx.values():
        series.sort()

    def to_gbp(amount: Decimal, currency: str, on: date) -> Decimal:
        if currency == LOCAL_CURRENCY:
            return money(amount)
        series = fx[currency]
        idx = bisect.bisect_right([d for d, _ in series], on) - 1
        return money(amount * series[max(idx, 0)][1])

    ekko = {r["EBELN"]: r for r in t["EKKO"]}
    eban = {(r["BANFN"], r["BNFPO"]): r for r in t["EBAN"]}
    eket = {(r["EBELN"], r["EBELP"]): r for r in t["EKET"]}
    rbkp = {(r["BELNR"], r["GJAHR"]): r for r in t["RBKP"]}

    gr, ir = defaultdict(list), defaultdict(list)
    for r in t["EKBE"]:
        sign = -1 if r["SHKZG"] == "H" else 1
        rec = (parse_sap_date(r["BUDAT"]), sign * Decimal(r["MENGE"]), sign * Decimal(r["AREWR"]), r["BWART"])
        (gr if r["VGABE"] == "1" else ir)[(r["EBELN"], r["EBELP"])].append(rec)

    first_invoice_date: dict[tuple, date] = {}
    for r in t["RSEG"]:
        key = (r["EBELN"], r["EBELP"])
        d = parse_sap_date(rbkp[(r["BELNR"], r["GJAHR"])]["BLDAT"])
        first_invoice_date[key] = min(d, first_invoice_date.get(key, d))

    items = [r for r in t["EKPO"] if r["LOEKZ"] != "L"]
    spend = Decimal(0)
    spend_by_supplier: dict[str, Decimal] = defaultdict(Decimal)
    pr_backed, pr_cycle_days, atf = 0, [], 0
    due, on_time, otif, lead_days = 0, 0, 0, []
    grir_open, grir_pos, grir_neg, grir_aged = 0, Decimal(0), Decimal(0), Decimal(0)

    for r in items:
        key = (r["EBELN"], r["EBELP"])
        header = ekko[r["EBELN"]]
        po_date = parse_sap_date(header["BEDAT"])
        value = to_gbp(Decimal(r["NETWR"]), header["WAERS"], po_date)
        spend += value
        spend_by_supplier[header["LIFNR"]] += value

        if r["BANFN"]:
            pr_backed += 1
            req = eban[(r["BANFN"], r["BNFPO"])]
            released = parse_sap_date(req["FRGDT"]) or parse_sap_date(req["BADAT"])
            pr_cycle_days.append((po_date - released).days)

        if key in first_invoice_date and first_invoice_date[key] < po_date:
            atf += 1

        receipts = gr.get(key, [])
        first_gr = min((d for d, q, _, bwart in receipts if bwart == "101"), default=None)
        if first_gr:
            lead_days.append((first_gr - po_date).days)
        eindt = parse_sap_date(eket[key]["EINDT"])
        if eindt + tol <= as_of:
            due += 1
            if first_gr and first_gr <= eindt + tol:
                on_time += 1
            received_in_window = sum((q for d, q, _, _ in receipts if d <= eindt + tol), Decimal(0))
            if received_in_window >= in_full * Decimal(r["MENGE"]):
                otif += 1

        balance = sum((v for _, _, v, _ in receipts), Decimal(0)) - sum((v for _, _, v, _ in ir.get(key, [])), Decimal(0))
        if balance >= CENT:
            grir_open += 1
            grir_pos += balance
            last_gr = max(d for d, _, _, _ in receipts)
            if (as_of - last_gr).days > KPI_RULES["grir_aging_threshold_days"]:
                grir_aged += balance
        elif balance <= -CENT:
            grir_neg += -balance

    # Invoices and payments
    fi_to_invoice = {(r["BUKRS"], r["BELNR"], r["GJAHR"]): (r["AWKEY"][:10], r["AWKEY"][10:]) for r in t["BKPF"]}
    cleared = {}
    for r in t["BSAK"]:
        cleared[fi_to_invoice[(r["BUKRS"], r["BELNR"], r["GJAHR"])]] = parse_sap_date(r["AUGDT"])

    groups: dict[tuple, list] = defaultdict(list)
    for r in t["RBKP"]:
        groups[(r["LIFNR"], normalise_reference(r["XBLNR"]), Decimal(r["RMWWR"]))].append(
            (parse_sap_date(r["BUDAT"]), r["GJAHR"], r["BELNR"]))
    duplicates = 0
    for docs in groups.values():
        docs.sort()
        for prev, cur in zip(docs, docs[1:]):
            if (cur[0] - prev[0]).days <= KPI_RULES["duplicate_window_days"]:
                duplicates += 1

    blocked, paid, paid_on_time, paid_early, days_to_pay = 0, 0, 0, 0, []
    open_count, open_value, overdue_open = 0, Decimal(0), 0
    for r in t["RBKP"]:
        if r["ZLSPR"]:
            blocked += 1
        bldat, budat = parse_sap_date(r["BLDAT"]), parse_sap_date(r["BUDAT"])
        due_date = parse_sap_date(r["ZFBDT"]) + timedelta(days=int(r["ZBD1T"]))
        augdt = cleared.get((r["BELNR"], r["GJAHR"]))
        if augdt:
            paid += 1
            days_to_pay.append((augdt - bldat).days)
            paid_on_time += augdt <= due_date
            paid_early += augdt < due_date - timedelta(days=KPI_RULES["early_payment_days"])
        else:
            open_count += 1
            open_value += to_gbp(Decimal(r["RMWWR"]), r["WAERS"], budat)
            overdue_open += due_date < as_of

    top10 = sum(sorted(spend_by_supplier.values(), reverse=True)[:10], Decimal(0))
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0

    return {
        "po_items": len(items),
        "spend_gbp": float(spend),
        "pr_backed_rate": pr_backed / len(items),
        "avg_pr_to_po_days": mean(pr_cycle_days),
        "after_the_fact_items": atf,
        "due_items": due,
        "on_time_rate": on_time / due,
        "otif_rate": otif / due,
        "avg_po_to_first_gr_days": mean(lead_days),
        "grir_open_items": grir_open,
        "grir_gr_not_invoiced_gbp": float(grir_pos),
        "grir_invoiced_not_received_gbp": float(grir_neg),
        "grir_over_90_days_gbp": float(grir_aged),
        "invoices": len(t["RBKP"]),
        "blocked_invoice_rate": blocked / len(t["RBKP"]),
        "duplicate_invoice_suspects": duplicates,
        "paid_invoices": paid,
        "paid_on_time_rate": paid_on_time / paid,
        "paid_early_rate": paid_early / paid,
        "avg_days_to_pay": mean(days_to_pay),
        "open_invoices": open_count,
        "open_invoice_value_gbp": float(open_value),
        "overdue_open_invoices": overdue_open,
        "top10_supplier_spend_share": float(top10 / spend),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def write_outputs(t: dict[str, list[dict]], out: Path, args, as_of: date):
    out.mkdir(parents=True, exist_ok=True)
    for name in sorted(t):
        rows = t[name]
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    manifest = {
        "source_system": "S4H-SYNTHETIC",
        "client": MANDT,
        "company_code": COMPANY_CODE,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": args.seed,
        "scale": args.scale,
        "period_start": args.start,
        "period_end": args.end,
        "as_of_date": as_of.isoformat(),
        "row_counts": {name: len(rows) for name, rows in sorted(t.items())},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    expected = {"as_of_date": as_of.isoformat(), "rules": KPI_RULES,
                "metrics": compute_expected_metrics(t, as_of)}
    (out / "expected_metrics.json").write_text(json.dumps(expected, indent=2))
    return manifest, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="output", help="output folder for the CSV extracts")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scale", type=float, default=1.0, help="volume multiplier (1.0 = ~3.8k POs)")
    parser.add_argument("--start", default="2024-10-01")
    parser.add_argument("--end", default="2026-09-30")
    parser.add_argument("--as-of", default="2026-10-05", help="extraction date")
    args = parser.parse_args()

    start, end, as_of = (date.fromisoformat(x) for x in (args.start, args.end, args.as_of))
    tables = P2PGenerator(args.seed, args.scale, start, end, as_of).run()
    manifest, expected = write_outputs(tables, Path(args.out), args, as_of)

    print(f"Wrote {len(manifest['row_counts'])} tables to {args.out}/")
    for name, count in manifest["row_counts"].items():
        print(f"  {name:<6} {count:>7,}")
    print("\nExpected KPIs (ground truth for pipeline tests):")
    for name, value in expected["metrics"].items():
        print(f"  {name:<34} {value:,.4f}" if isinstance(value, float) else f"  {name:<34} {value:,}")


if __name__ == "__main__":
    main()
