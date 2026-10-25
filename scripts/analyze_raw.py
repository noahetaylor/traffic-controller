import pandas as pd
from ee_paths import EE

df = pd.read_csv(EE("don_mills_lawrence_raw.csv"))
df["start_time"] = pd.to_datetime(df["start_time"])
df = df.sort_values("start_time").reset_index(drop=True)
print("Bins:", len(df), "| Time range:", df["start_time"].min().time(), "->", df["start_time"].max().time())

appr = ["n","s","e","w"]; moves = ["l","t","r"]; modes = ["cars","truck","bus"]
for a in appr:
    for m in moves:
        df[f"{a}_{m}"] = df[[f"{a}_appr_{mode}_{m}" for mode in modes]].sum(axis=1)
    df[f"{a}_tot"] = df[[f"{a}_l",f"{a}_t",f"{a}_r"]].sum(axis=1)

print("\n=== Per-approach 14-hour vehicle totals & turning split ===")
for a in appr:
    tot = int(df[f"{a}_tot"].sum())
    l,t,r = (int(df[f"{a}_{m}"].sum()) for m in moves)
    if tot:
        print(f"{a.upper()} leg: total {tot:6d} |  L {l:5d} ({100*l/tot:4.1f}%)   T {t:5d} ({100*t/tot:4.1f}%)   R {r:5d} ({100*r/tot:4.1f}%)")

ns = int(df[["n_tot","s_tot"]].to_numpy().sum()); ew = int(df[["e_tot","w_tot"]].to_numpy().sum())
print(f"\nDon Mills (N+S): {ns}   Lawrence (E+W): {ew}   balance {min(ns,ew)/max(ns,ew):.2f}   grand total {ns+ew}")

df["allbin"] = df[[f"{a}_tot" for a in appr]].sum(axis=1)
df["hour"] = df["start_time"].dt.hour
hourly = df.groupby("hour")["allbin"].sum()
print("\n=== Vehicles per hour (all approaches) ===")
for h,v in hourly.items():
    print(f"{h:02d}:00  {int(v):5d}  {'#'*int(v/100)}")

roll = df.set_index("start_time")["allbin"].rolling(4).sum()
am = roll[roll.index.hour < 12]; pm = roll[roll.index.hour >= 12]
print(f"\nAM peak hour starts ~{(am.idxmax()-pd.Timedelta(minutes=45)).time()} ({int(am.max())} veh)")
print(f"PM peak hour starts ~{(pm.idxmax()-pd.Timedelta(minutes=45)).time()} ({int(pm.max())} veh)")
