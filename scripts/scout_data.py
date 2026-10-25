import pandas as pd, glob, sys
from pathlib import Path

cands = (glob.glob(str(Path.home()/"Downloads"/"*summary*.csv"))
         + glob.glob("*summary*.csv"))
if not cands:
    print("No summary CSV found. Paste its full path into this script and rerun.")
    sys.exit()

path = cands[0]
print("Loading:", path)
df = pd.read_csv(path, low_memory=False)
print("Rows:", len(df), "| Cols:", df.shape[1])

print("\n--- COLUMNS ---")
for col in df.columns:
    print("  ", col)

print("\n--- COLUMNS THAT LOOK LIKE APPROACH VOLUMES ---")
toks = ("veh","car","truck","bus","vol","total","approach","_n","_s","_e","_w",
        "nb","sb","eb","wb","north","south","east","west")
for col in df.columns:
    lc = col.lower()
    if any(t in lc for t in toks):
        print("  ", col)

print("\n--- FIRST 2 ROWS ---")
print(df.head(2).to_string())
