from pathlib import Path

p = Path('tools/build_historical_episode_evidence.py')
s = p.read_text()
old = '    df = build_full_v2_state(df)\n'
new = old + '    # Match the archived canonical validation window exactly.\n    df = df.loc[:pd.Timestamp("2026-09-04")].copy()\n'
if new not in s:
    if old not in s:
        raise SystemExit('sample-end anchor missing')
    s = s.replace(old, new, 1)
p.write_text(s)
print('Pinned historical evidence reconstruction to canonical sample end 2026-09-04')
