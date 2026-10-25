import pandas as pd, glob
from pathlib import Path
from ee_paths import EE

# 1) Get our intersection's identifiers from the summary
summ = pd.read_csv((glob.glob(str(Path.home()/"Downloads"/"*most_recent_summary*.csv"))
                    + glob.glob("*summary*.csv"))[0], low_memory=False)
summ["px"] = pd.to_numeric(summ["px"], errors="coerce")
mask = (summ["location_name"].str.lower().str.contains("don mills")
        & summ["location_name"].str.lower().str.contains("lawrence")
        & (summ["px"] == 402))
row = summ[mask].iloc[0]
count_id = int(row["latest_count_id"])
centreline = row.get("centreline_id")
print("Target:", row["location_name"])
print("count_id:", count_id, "| centreline_id:", centreline, "| px:", row["px"])
print("coords:", row["latitude"], row["longitude"], "| date:", row["latest_count_date"])

# 2) Locate the raw file
raws = glob.glob(str(Path.home()/"Downloads"/"*raw*.csv")) + glob.glob("*raw*.csv")
if not raws:
    raise SystemExit("No raw CSV found in Downloads. Download+unzip the raw decade file first.")
rawpath = raws[0]
print("\nRaw file:", rawpath)

cols = list(pd.read_csv(rawpath, nrows=5).columns)
print("\n--- RAW COLUMNS ---")
for c in cols: print("  ", c)

# 3) Decide how to match our intersection in the raw file
if "count_id" in cols:       key, val = "count_id", count_id
elif "centreline_id" in cols: key, val = "centreline_id", centreline
elif "location_name" in cols: key, val = "location_name", None
else: raise SystemExit("No usable key column in raw file; paste the RAW COLUMNS above to me.")
print(f"\nMatching on: {key}")

# 4) Chunk through the raw file and keep only our intersection
keep = []
for chunk in pd.read_csv(rawpath, chunksize=200_000, low_memory=False):
    if key == "location_name":
        m = (chunk["location_name"].str.lower().str.contains("don mills", na=False)
             & chunk["location_name"].str.lower().str.contains("lawrence", na=False))
    else:
        m = chunk[key] == val
    if m.any(): keep.append(chunk[m])
sub = pd.concat(keep, ignore_index=True) if keep else pd.DataFrame(columns=cols)
print(f"\nMatched rows: {len(sub)}")

# If we matched by a non-count key, narrow to the most recent count date
if key != "count_id" and "count_date" in sub.columns and len(sub):
    latest = sub["count_date"].max()
    sub = sub[sub["count_date"] == latest]
    print("Narrowed to latest count_date:", latest, "->", len(sub), "rows")

if len(sub):
    print("\nUnique location_name(s):", sub["location_name"].unique() if "location_name" in sub else "n/a")
    sub.to_csv(EE("don_mills_lawrence_raw.csv"), index=False)
    print("Saved -> don_mills_lawrence_raw.csv")
    print("\n--- FIRST 3 ROWS ---")
    print(sub.head(3).to_string())
else:
    print("No rows matched — paste the RAW COLUMNS block to me and we will adjust the key.")
