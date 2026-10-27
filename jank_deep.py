# -*- coding: utf-8 -*-
"""Deep-dive into the worst jank moments of com.xlff.xlffand."""
from perfetto.trace_processor import TraceProcessor, TraceProcessorConfig
from collections import defaultdict

TRACE_PATH = r"C:\Users\sunny\Downloads\perfetto\trace_file.perfetto-trace"
SHELL = r"C:\Users\sunny\.local\share\perfetto\prebuilts\trace_processor_shell.exe"
tp = TraceProcessor(file_path=TRACE_PATH, config=TraceProcessorConfig(bin_path=SHELL))
TRACE_START = list(tp.query("SELECT int_value AS v FROM metadata WHERE name='tracing_started_ns'"))[0].v

def q(sql):
    return list(tp.query(sql))

def ms(ns):
    return (ns or 0) / 1e6

def t_rel(ts):
    return (ts - TRACE_START) / 1e9

APP = "com.xlff.xlffand"

# Key jank windows (frame present ts ± margin), from previous analysis
# Worst frames start around these times (relative seconds converted to abs ns)
windows = [
    ("startup bind+first frame", 2.00, 3.80),
    ("jank 1809ms", 4.10, 6.00),
    ("jank cluster ~6s", 6.00, 6.60),
    ("jank cluster ~8s", 8.00, 8.60),
    ("jank 677ms @9s", 9.00, 9.80),
    ("jank ~11.8-12.4s", 11.70, 12.40),
    ("jank ~13.7-14.0s", 13.60, 14.10),
    ("jank ~15.2-15.6s", 15.15, 15.65),
    ("jank ~17.1s", 17.05, 17.45),
]

print("=" * 72)
print("A) MAIN THREAD SLICE TREE during worst jank windows")
print("=" * 72)
for label, t0, t1 in windows:
    ts0 = TRACE_START + int(t0 * 1e9)
    ts1 = TRACE_START + int(t1 * 1e9)
    print(f"\n--- {label}  t=[{t0:.2f}s, {t1:.2f}s] ---")
    rows = q(f"""
      SELECT s.ts, s.dur, s.name, s.depth
      FROM slice s
      JOIN thread_track tt ON s.track_id = tt.id
      JOIN thread t ON tt.utid = t.utid
      JOIN process p ON t.upid = p.upid
      WHERE p.name = '{APP}' AND t.is_main_thread = 1
        AND s.ts < {ts1} AND s.ts + s.dur > {ts0}
        AND s.dur > 5000000
      ORDER BY s.ts, s.depth
      LIMIT 80
    """)
    if not rows:
        print("  (no slices >5ms)")
        continue
    for r in rows:
        indent = "  " * r.depth
        print(f"  t={t_rel(r.ts):7.3f}s d={r.depth} {ms(r.dur):8.2f}ms {indent}{r.name[:70]}")

# Deeper look inside the 1.8s frame: all slices >10ms with parent context
print("\n" + "=" * 72)
print("B) ALL slices >10ms in t=[4.15, 6.05] for main app (all threads)")
print("=" * 72)
ts0 = TRACE_START + int(4.15e9)
ts1 = TRACE_START + int(6.05e9)
for r in q(f"""
  SELECT t.name AS thread, t.tid, t.is_main_thread, s.ts, s.dur, s.name, s.depth
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{APP}'
    AND s.ts < {ts1} AND s.ts + s.dur > {ts0}
    AND s.dur > 10000000
  ORDER BY s.dur DESC
  LIMIT 50
"""):
    main = "M" if r.is_main_thread else " "
    print(f"  t={t_rel(r.ts):7.3f}s {ms(r.dur):8.2f}ms [{main}] {r.thread[:20]:20} d={r.depth} {r.name[:65]}")

# Compose recomposition details
print("\n" + "=" * 72)
print("C) Compose / recompose / measureAndLayout all slow")
print("=" * 72)
for r in q(f"""
  SELECT s.ts, s.dur, s.name, t.name AS thread
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{APP}'
    AND (s.name LIKE 'Compose%' OR s.name LIKE '%recompose%' OR s.name LIKE '%measureAndLayout%'
         OR s.name LIKE '%AndroidOwner%' OR s.name LIKE '%Choreographer%doFrame%')
    AND s.dur > 30000000
  ORDER BY s.dur DESC LIMIT 40
"""):
    print(f"  t={t_rel(r.ts):7.3f}s {ms(r.dur):8.2f}ms {r.thread[:18]:18} {r.name[:60]}")

# Image decode / AssetInputStream correlation
print("\n" + "=" * 72)
print("D) Image decode / AssetInputStream / BitmapFactory-like slices")
print("=" * 72)
for r in q(f"""
  SELECT s.ts, s.dur, s.name, t.name AS thread, t.is_main_thread
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{APP}'
    AND (s.name LIKE '%AssetInputStream%' OR s.name LIKE '%InputStream%' OR s.name LIKE '%Bitmap%'
         OR s.name LIKE '%ImageDecoder%' OR s.name LIKE '%decode%' OR s.name LIKE '%nflate%'
         OR s.name LIKE '%Open dex%' OR s.name LIKE '%OpenDex%')
  ORDER BY s.dur DESC LIMIT 30
"""):
    main = "M" if r.is_main_thread else " "
    print(f"  t={t_rel(r.ts):7.3f}s {ms(r.dur):8.2f}ms [{main}] {r.thread[:18]:18} {r.name[:70]}")

# AsyncTask / ExoPlayer heavy
print("\n" + "=" * 72)
print("E) Background threads with long slices (>50ms)")
print("=" * 72)
for r in q(f"""
  SELECT t.name AS thread, t.tid, s.ts, s.dur, s.name
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{APP}' AND t.is_main_thread = 0 AND s.dur > 50000000
  ORDER BY s.dur DESC LIMIT 30
"""):
    print(f"  t={t_rel(r.ts):7.3f}s {ms(r.dur):8.2f}ms {r.thread[:20]:20} {r.name[:55]}")

# Input events during jank
print("\n" + "=" * 72)
print("F) Input events on main thread (all)")
print("=" * 72)
for r in q(f"""
  SELECT s.ts, s.dur, s.name
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{APP}' AND t.is_main_thread = 1
    AND (s.name LIKE 'dispatchInputEvent%' OR s.name LIKE 'deliverInputEvent%'
         OR s.name LIKE 'ViewPostIme%' OR s.name LIKE 'View#onTouchEvent%')
  ORDER BY s.ts LIMIT 50
"""):
    flag = " <== SLOW" if r.dur > 16_000_000 else ""
    print(f"  t={t_rel(r.ts):7.3f}s {ms(r.dur):8.2f}ms {r.name[:70]}{flag}")

# Startup sequence
print("\n" + "=" * 72)
print("G) App startup sequence (bindApplication → first frames)")
print("=" * 72)
for r in q(f"""
  SELECT s.ts, s.dur, s.name, s.depth
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{APP}' AND t.is_main_thread = 1
    AND s.ts < {TRACE_START + int(5e9)}
    AND s.dur > 5000000
    AND s.depth <= 3
  ORDER BY s.ts, s.depth LIMIT 60
"""):
    print(f"  t={t_rel(r.ts):7.3f}s d={r.depth} {ms(r.dur):8.2f}ms {r.name[:70]}")

# CPU during the 1.8s jank - was main thread running or blocked?
print("\n" + "=" * 72)
print("H) Main thread state during t=[4.15, 6.00]")
print("=" * 72)
for r in q(f"""
  SELECT state, io_wait, SUM(dur)/1e6 AS total_ms, COUNT(*) AS n, MAX(dur)/1e6 AS max_ms
  FROM thread_state
  JOIN thread USING(utid)
  JOIN process USING(upid)
  WHERE process.name = '{APP}' AND thread.is_main_thread = 1
    AND ts < {TRACE_START + int(6.0e9)} AND ts + dur > {TRACE_START + int(4.15e9)}
  GROUP BY state, io_wait ORDER BY total_ms DESC
"""):
    print(f"  state={r.state:4} io={r.io_wait} n={r.n:4} tot={r.total_ms:8.1f}ms max={r.max_ms:7.2f}ms")

print("\nDONE")
