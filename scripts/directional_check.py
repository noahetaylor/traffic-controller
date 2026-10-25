import pandas as pd
from ee_paths import EE

df = pd.read_csv(EE("don_mills_lawrence_raw.csv"))
df["start_time"] = pd.to_datetime(df["start_time"])
df["hour"] = df["start_time"].dt.hour

appr = ["n","s","e","w"]; modes = ["cars","truck","bus"]
for a in appr:
    df[f"{a}_tot"] = df[[f"{a}_appr_{mode}_{m}" for mode in modes for m in ["l","t","r"]]].sum(axis=1)

def leg_share(window, label):
    w = df[df["hour"].isin(window)]
    tot = sum(w[f"{a}_tot"].sum() for a in appr)
    print(f"\n{label} (hours {window[0]:02d}-{window[-1]:02d}):  {int(tot)} veh")
    for a in appr:
        v = int(w[f"{a}_tot"].sum())
        print(f"   {a.upper()} leg (entering from {a.upper()}): {v:5d}  ({100*v/tot:4.1f}%)")

leg_share([8], "AM PEAK")
leg_share([17], "PM PEAK")

print("\nReminder: N/S legs = Don Mills, E/W legs = Lawrence.")
print("Look for whether the busiest leg CHANGES between AM and PM.")
