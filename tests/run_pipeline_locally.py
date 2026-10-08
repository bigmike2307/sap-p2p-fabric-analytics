#!/usr/bin/env python3
"""
Run the Fabric notebooks end to end on a local Spark session.

Generates a fresh synthetic SAP extract, then executes notebooks 01-04 in order with the
same code that runs in Fabric. Only the parameter cell is overridden (local paths, Parquet
instead of Delta). Notebook 04 raises if any data-quality or KPI reconciliation check
fails, so a zero exit code means the whole pipeline is correct.

    pip install -r requirements-dev.txt
    python tests/run_pipeline_locally.py --scale 0.5
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ["nb_01_bronze_ingest", "nb_02_silver_conform", "nb_03_gold_model", "nb_04_data_quality"]


def ensure_java():
    """Use a pip-installed JDK (jdk4py) when no working Java is on the machine."""
    if os.environ.get("JAVA_HOME"):
        return
    if shutil.which("java"):  # macOS ships a /usr/bin/java stub that fails without a JDK
        if subprocess.run(["java", "-version"], capture_output=True).returncode == 0:
            return
    try:
        import jdk4py
        os.environ["JAVA_HOME"] = str(jdk4py.JAVA_HOME)
    except ImportError:
        sys.exit("Java not found: install a JDK 17+ or `pip install jdk4py`.")


def run_notebook(name: str, spark, overrides: dict):
    notebook = json.loads((ROOT / "fabric" / "notebooks" / f"{name}.ipynb").read_text())
    namespace = {"spark": spark, "display": lambda df, *a, **k: df.show(20, truncate=False)}
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        exec(compile("".join(cell["source"]), name, "exec"), namespace)
        if "parameters" in cell["metadata"].get("tags", []):
            namespace.update(overrides)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="0.5", help="data volume passed to the generator")
    parser.add_argument("--seed", default="42")
    parser.add_argument("--keep", action="store_true", help="keep the working folder for inspection")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="p2p_local_"))
    landing = work / "landing"
    subprocess.run([sys.executable, str(ROOT / "data_generator" / "generate_sap_p2p.py"),
                    "--out", str(landing), "--scale", args.scale, "--seed", args.seed],
                   check=True, stdout=subprocess.DEVNULL)

    ensure_java()
    from pyspark.sql import SparkSession

    spark = (SparkSession.builder.master("local[*]").appName("p2p-local")
             .config("spark.sql.catalogImplementation", "in-memory")
             .config("spark.sql.warehouse.dir", str(work / "warehouse"))
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.ui.enabled", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    overrides = {"LANDING_PATH": str(landing), "TABLE_FORMAT": "parquet"}
    try:
        for name in NOTEBOOKS:
            started = time.time()
            print(f"\n=== {name} ===")
            run_notebook(name, spark, overrides)
            print(f"--- {name} finished in {time.time() - started:.1f}s")
    finally:
        spark.stop()
        if args.keep:
            print(f"\nWorking folder kept at {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
    print("\nPipeline passed: all notebooks ran and every data-quality check succeeded.")


if __name__ == "__main__":
    main()
