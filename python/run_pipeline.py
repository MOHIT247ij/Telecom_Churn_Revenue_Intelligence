"""Run the full pipeline end-to-end:  python run_pipeline.py"""
import subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["01_generate_data.py", "02_data_cleaning.py", "03_eda.py", "04_churn_model.py",
         "05_revenue_intelligence.py", "06_build_powerbi_model.py", "07_load_sql.py"]

for step in STEPS:
    print(f"\n{'=' * 70}\n▶ {step}\n{'=' * 70}")
    t = time.time()
    r = subprocess.run([sys.executable, step], cwd=HERE)
    if r.returncode != 0:
        sys.exit(f"✖ {step} failed")
    print(f"✔ {step} done in {time.time() - t:.1f}s")
print("\nPipeline complete. Open powerbi/ and follow Dashboard_Build_Guide.md")
