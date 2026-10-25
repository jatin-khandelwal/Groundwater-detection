"""
tidy_project.py
Project folder ko saaf karta hai. KUCH DELETE NAHI KARTA, sirf archive folder mein MOVE karta hai.

Pehle dry-run (kuch move nahi hota, sirf plan dikhata hai aur tidy_plan.txt mein likhta hai):
    python scripts\\tidy_project.py
Plan theek lage to:
    python scripts\\tidy_project.py apply

Safety: agar koi file scripts/, notebooks/ ya root ki .py files mein naam se use hoti dikhe,
to wo MOVE NAHI hoti ("REFERENCED" likha aata hai). Archive folder project ke bahar banta hai:
    <project folder>_archive\\   (aur wahan archive_log.csv bhi)
"""
import csv
import shutil
import sys
from pathlib import Path

root = Path.cwd()
archive = root.parent / (root.name + "_archive")
apply = len(sys.argv) > 1 and sys.argv[1].lower() == "apply"

# (kahan se, pattern/naam, archive ke andar folder, wajah)
RULES = [
    (".", "Screenshot*.png", "root_misc", "screenshot"),
    (".", "region.csv", "root_misc", "test file"),
    (".", "region.nc", "root_misc", "test file"),
    (".", "run_log.txt", "root_misc", "purana log"),
    (".", "jaipur_rainfall_2020.json", "root_misc", "rainfall ka pehla test"),
    ("data/processed", "dataset_v2.csv", "processed_old", "purani, v2_1/v2_3 use karo"),
    ("data/processed", "dataset_v2_2.csv", "processed_old", "v2_3 isi ka superset hai"),
    ("data/processed", "dataset_v2_neighbors.csv", "processed_old", "intermediate, v2_1 se pehle"),
    ("data/processed", "groundwater_coordinate_subset.csv", "processed_old", "intermediate, sabse badi"),
    ("data/processed", "rainfall_daily_2004_2024.csv", "processed_old", "monthly file ban chuki hai, raw JSON se dobara ban sakti hai"),
    ("data/processed", "rainfall_normals.csv", "processed_old", "unverified, rainfall_normals_v2_1 use karo"),
    ("data/processed", "data_dictionary.csv", "processed_old", "purani dictionary"),
    ("data/processed", "data_dictionary_v2.csv", "processed_old", "purani dictionary"),
]

# Kin files ke andar naam dhoondhna hai (ye script khud nahi, warna sab 'referenced' dikhengi)
search_files = list((root / "scripts").glob("*.py")) + list(root.glob("*.py")) + \
    list((root / "notebooks").glob("*.ipynb"))
if (root / "backend").exists():
    search_files += list((root / "backend").rglob("*.py"))
search_files = [f for f in search_files if f.name != Path(__file__).name]
texts = {}
for f in search_files:
    try:
        texts[f] = f.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        pass


def referenced_in(name):
    return [f.name for f, t in texts.items() if name in t]


plan, lines = [], []
for folder, pat, dest, why in RULES:
    base = root / folder
    if not base.exists():
        continue
    for p in sorted(base.glob(pat)):
        if not p.is_file():
            continue
        refs = referenced_in(p.name)
        mb = p.stat().st_size / 1e6
        if refs:
            lines.append(f"[SKIP REFERENCED] {p.relative_to(root)}  ({mb:.1f} MB)  <- {', '.join(sorted(set(refs)))}")
        else:
            lines.append(f"[MOVE] {p.relative_to(root)}  ({mb:.1f} MB)  -> {dest}/   ({why})")
            plan.append((p, dest, why))

header = [f"Project: {root}", f"Archive: {archive}", f"Mode: {'APPLY' if apply else 'DRY RUN (kuch move nahi hoga)'}", ""]
total = sum(p.stat().st_size for p, _, _ in plan) / 1e6
footer = ["", f"Move hone wali files: {len(plan)}  (kul {total:.1f} MB)"]
out = "\n".join(header + lines + footer)
print(out)
(root / "tidy_plan.txt").write_text(out, encoding="utf-8")

if apply:
    archive.mkdir(exist_ok=True)
    log = archive / "archive_log.csv"
    new = not log.exists()
    with open(log, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["file", "moved_to", "mb", "reason"])
        for p, dest, why in plan:
            d = archive / dest
            d.mkdir(parents=True, exist_ok=True)
            target = d / p.name
            if target.exists():
                print("   exists, skip:", target)
                continue
            shutil.move(str(p), str(target))
            w.writerow([str(p.relative_to(root)), str(target), round(target.stat().st_size / 1e6, 2), why])
    print(f"\nMove ho gaya. Wapas chahiye to archive folder se utha lo. Log: {log}")
else:
    print("\nPlan theek lage to:  python scripts\\tidy_project.py apply")
