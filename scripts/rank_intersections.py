import pandas as pd, glob
from pathlib import Path
from ee_paths import EE

path = (glob.glob(str(Path.home()/"Downloads"/"*most_recent_summary*.csv"))
        + glob.glob(str(Path.home()/"Downloads"/"*summary*.csv"))
        + glob.glob("*summary*.csv"))[0]
df = pd.read_csv(path, low_memory=False)
print("Loaded", len(df), "counts")

for c in ["n_appr_vehicle","e_appr_vehicle","s_appr_vehicle","w_appr_vehicle",
          "total_vehicle","am_peak_vehicle","pm_peak_vehicle","count_duration"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

df["signalized"] = df["px"].notna()
df["ns"] = df["n_appr_vehicle"] + df["s_appr_vehicle"]
df["ew"] = df["e_appr_vehicle"] + df["w_appr_vehicle"]
df["lighter_street"] = df[["ns","ew"]].min(axis=1)
df["balance"] = df["lighter_street"] / df[["ns","ew"]].max(axis=1)
legs = df[["n_appr_vehicle","e_appr_vehicle","s_appr_vehicle","w_appr_vehicle"]]
df["min_leg_share"] = legs.min(axis=1) / df["total_vehicle"]

n0 = len(df)
base = df[df["signalized"]]
print(f"signalized:            {len(base)} / {n0}")
recent = base[base["count_duration"] == 14]
use = recent if len(recent) >= 25 else base
print(f"using {'14-hour counts' if use is recent else 'all durations'}: {len(use)}")
f = use[use["min_leg_share"] >= 0.05]
print(f"true 4-way (each leg >=5%): {len(f)}")
f = f[f["balance"] >= 0.5]
print(f"balanced (>=0.5):          {len(f)}")

top = f.sort_values("lighter_street", ascending=False).head(20).copy()
for c in ["total_vehicle","ns","ew","am_peak_vehicle","pm_peak_vehicle"]:
    top[c] = top[c].round(0).astype("Int64")
top["balance"] = top["balance"].round(2)
cols = ["location_name","total_vehicle","ns","ew","balance",
        "am_peak_vehicle","pm_peak_vehicle","px","latitude","longitude","latest_count_date"]
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
print("\n===== TOP CANDIDATES (busy on BOTH streets, signalized, 4-way) =====")
print(top[cols].to_string(index=False))
top[cols].to_csv(EE("candidate_intersections.csv"), index=False)
print("\nSaved -> candidate_intersections.csv")
