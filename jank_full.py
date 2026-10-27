# -*- coding: utf-8 -*-
"""Full jank analysis for Android Perfetto trace (with Frame Timeline)."""
from perfetto.trace_processor import TraceProcessor, TraceProcessorConfig
from collections import defaultdict

TRACE_PATH = r"C:\Users\sunny\Downloads\perfetto\trace_file.perfetto-trace"
SHELL = r"C:\Users\sunny\.local\share\perfetto\prebuilts\trace_processor_shell.exe"
cfg = TraceProcessorConfig(bin_path=SHELL)
tp = TraceProcessor(file_path=TRACE_PATH, config=cfg)

def q(sql):
    return list(tp.query(sql))

def ms(ns):
    return (ns or 0) / 1e6

# Get trace start from metadata
meta = q("SELECT name, int_value FROM metadata WHERE name = 'tracing_started_ns'")
TRACE_START = meta[0].int_value if meta else None

def t_rel(ts):
    if TRACE_START is None or ts is None:
        return 0.0
    return (ts - TRACE_START) / 1e9

# ---------------------------------------------------------------
# 0) Metadata / frame timeline availability
# ---------------------------------------------------------------
print("=" * 72)
print("0) TRACE INFO")
print("=" * 72)
for r in q("""
  SELECT name, str_value FROM metadata
  WHERE name IN ('android_build_fingerprint','android_soc_model','android_sdk_version','system_release')
"""):
    print(f"  {r.name}: {r.str_value}")

for r in q("SELECT (MAX(ts+dur)-MIN(ts))/1e9 AS d FROM slice WHERE dur>=0"):
    print(f"  slice duration: {r.d:.3f}s")
print(f"  TRACE_START ns: {TRACE_START}")

for r in q("SELECT COUNT(*) AS n FROM actual_frame_timeline_slice"):
    print(f"  actual_frame_timeline_slice: {r.n}")
for r in q("SELECT COUNT(*) AS n FROM expected_frame_timeline_slice"):
    print(f"  expected_frame_timeline_slice: {r.n}")

# Processes with frame timeline
print("\n  processes with actual frames:")
for r in q("""
  SELECT p.name, p.pid, COUNT(*) AS frames,
         SUM(CASE WHEN a.jank_type IS NOT NULL AND a.jank_type != 'None' THEN 1 ELSE 0 END) AS janky
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
  GROUP BY a.upid ORDER BY frames DESC
"""):
    print(f"    {(r.name or '?'):40} pid={r.pid:6} frames={r.frames:5} janky={r.janky}")

# ---------------------------------------------------------------
# 1) Global jank breakdown
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("1) JANK TYPE BREAKDOWN (all apps)")
print("=" * 72)
total_frames = q("SELECT COUNT(*) AS n FROM actual_frame_timeline_slice")[0].n
total_janky = q("""
  SELECT COUNT(*) AS n FROM actual_frame_timeline_slice
  WHERE jank_type IS NOT NULL AND jank_type != 'None'
""")[0].n
print(f"  total actual frames: {total_frames}, janky: {total_janky} ({100*total_janky/max(total_frames,1):.1f}%)")

for r in q("""
  SELECT jank_type, jank_severity_type, COUNT(*) AS n,
         AVG(dur)/1e6 AS avg_ms, MAX(dur)/1e6 AS max_ms, SUM(dur)/1e6 AS total_ms
  FROM actual_frame_timeline_slice
  WHERE jank_type IS NOT NULL AND jank_type != 'None'
  GROUP BY jank_type, jank_severity_type
  ORDER BY n DESC
"""):
    sev = r.jank_severity_type or "?"
    print(f"  [{sev:10}] {r.jank_type:55} n={r.n:5} avg={r.avg_ms:7.2f}ms max={r.max_ms:8.2f}ms tot={r.total_ms:8.1f}ms")

# ---------------------------------------------------------------
# 2) Per-app frame stats
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("2) PER-APP FRAME STATS")
print("=" * 72)
print(f"  {'process':40} {'pid':>6} {'frames':>7} {'janky':>6} {'jank%':>6} {'avg_ms':>8} {'p95_ms':>8} {'max_ms':>8} {'late%':>6}")
for r in q("""
  SELECT
    p.name AS process_name, p.pid AS pid,
    COUNT(*) AS frames,
    SUM(CASE WHEN a.jank_type IS NOT NULL AND a.jank_type != 'None' THEN 1 ELSE 0 END) AS janky,
    AVG(a.dur)/1e6 AS avg_ms,
    MAX(a.dur)/1e6 AS max_ms,
    SUM(CASE WHEN a.present_type != 'On-time Present' THEN 1 ELSE 0 END) AS late_frames,
    SUM(CASE WHEN a.on_time_finish = 0 THEN 1 ELSE 0 END) AS not_on_time
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
  GROUP BY a.upid
  HAVING frames >= 5
  ORDER BY janky DESC, frames DESC
"""):
    jank_pct = 100 * r.janky / r.frames
    late_pct = 100 * r.late_frames / r.frames
    # p95 via separate query would be heavy; approximate later
    print(f"  {(r.process_name or '?'):40} {r.pid or 0:6} {r.frames:7} {r.janky:6} {jank_pct:5.1f}% {r.avg_ms:8.2f} {'':>8} {r.max_ms:8.2f} {late_pct:5.1f}%")

# p95 per app for top apps
print("\n  p95 duration (ms) per app:")
for r in q("""
  SELECT p.name AS process_name, a.dur
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
"""):
    pass  # will do in python

by_app = defaultdict(list)
for r in q("""
  SELECT p.name AS process_name, a.dur AS dur
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
"""):
    by_app[r.process_name or "?"].append(r.dur)

for name, durs in sorted(by_app.items(), key=lambda x: -len(x[1])):
    if len(durs) < 5:
        continue
    durs_sorted = sorted(durs)
    p50 = durs_sorted[len(durs_sorted)//2] / 1e6
    p90 = durs_sorted[int(len(durs_sorted)*0.90)] / 1e6
    p95 = durs_sorted[int(len(durs_sorted)*0.95)] / 1e6
    p99 = durs_sorted[min(int(len(durs_sorted)*0.99), len(durs_sorted)-1)] / 1e6
    print(f"    {name[:40]:40} p50={p50:7.2f} p90={p90:7.2f} p95={p95:7.2f} p99={p99:7.2f}")

# ---------------------------------------------------------------
# 3) Worst frames overall
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("3) WORST 40 FRAMES BY DURATION")
print("=" * 72)
for r in q("""
  SELECT p.name AS process_name, p.pid, a.ts, a.dur, a.jank_type, a.jank_severity_type,
         a.layer_name, a.present_type, a.on_time_finish, a.display_frame_token, a.surface_frame_token
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
  ORDER BY a.dur DESC LIMIT 40
"""):
    print(f"  t={t_rel(r.ts):7.3f}s {(r.process_name or '?')[:28]:28} {ms(r.dur):8.2f}ms "
          f"jank={str(r.jank_type)[:40]:40} present={str(r.present_type)[:20]:20} layer={str(r.layer_name)[:35]}")

# ---------------------------------------------------------------
# 4) Main app focus: com.xlff.xlffand if present, else top janky
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("4) MAIN APP FRAME TIMELINE DETAIL")
print("=" * 72)
# pick app with most janky frames
main_app_row = q("""
  SELECT p.name AS process_name
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
  WHERE a.jank_type IS NOT NULL AND a.jank_type != 'None'
  GROUP BY a.upid ORDER BY COUNT(*) DESC LIMIT 1
""")
main_app = main_app_row[0].process_name if main_app_row else "com.xlff.xlffand"
print(f"  focus app: {main_app}")

# janky frames list for main app
print(f"\n  janky frames for {main_app}:")
for r in q(f"""
  SELECT a.ts, a.dur, a.jank_type, a.jank_severity_type, a.layer_name, a.present_type,
         a.display_frame_token, a.surface_frame_token,
         e.dur AS expected_dur, (a.dur - e.dur)/1e6 AS over_ms
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
  LEFT JOIN expected_frame_timeline_slice e
    ON e.upid = a.upid AND e.display_frame_token = a.display_frame_token
  WHERE p.name = '{main_app}'
    AND a.jank_type IS NOT NULL AND a.jank_type != 'None'
  ORDER BY a.dur DESC LIMIT 40
"""):
    print(f"    t={t_rel(r.ts):7.3f}s {ms(r.dur):7.2f}ms exp={ms(r.expected_dur):7.2f}ms over={r.over_ms:+7.2f}ms "
          f"{str(r.jank_type)[:35]:35} sev={r.jank_severity_type} present={r.present_type}")

# expected budget distribution for main app
print(f"\n  expected frame budget for {main_app}:")
for r in q(f"""
  SELECT e.dur/1e6 AS exp_ms, COUNT(*) AS n
  FROM expected_frame_timeline_slice e
  LEFT JOIN process p USING(upid)
  WHERE p.name = '{main_app}'
  GROUP BY e.dur ORDER BY n DESC LIMIT 10
"""):
    print(f"    {r.exp_ms:.2f} ms x {r.n}")

# ---------------------------------------------------------------
# 5) Choreographer#doFrame
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("5) Choreographer#doFrame (main threads)")
print("=" * 72)
for app in ["com.xlff.xlffand", main_app, "com.tencent.mm", "com.miui.home"]:
    rows = q(f"""
      SELECT s.ts, s.dur
      FROM slice s
      JOIN thread_track tt ON s.track_id = tt.id
      JOIN thread t ON tt.utid = t.utid
      JOIN process p ON t.upid = p.upid
      WHERE p.name = '{app}' AND t.is_main_thread = 1
        AND s.name LIKE 'Choreographer#doFrame%'
        AND s.dur >= 0
    """)
    if not rows:
        continue
    durs = [r.dur for r in rows]
    n = len(durs)
    durs_s = sorted(durs)
    p95 = durs_s[int(n*0.95)] / 1e6
    o16 = sum(1 for d in durs if d > 16_000_000)
    o33 = sum(1 for d in durs if d > 33_000_000)
    o64 = sum(1 for d in durs if d > 64_000_000)
    o100 = sum(1 for d in durs if d > 100_000_000)
    print(f"\n  {app}: n={n} avg={sum(durs)/n/1e6:.2f}ms p95={p95:.2f}ms max={max(durs)/1e6:.2f}ms")
    print(f"    >16ms={o16} ({100*o16/n:.1f}%)  >33ms={o33}  >64ms={o64}  >100ms={o100}")
    print("    top 15 slowest:")
    for r in sorted(rows, key=lambda x: x.dur, reverse=True)[:15]:
        print(f"      t={t_rel(r.ts):7.3f}s {ms(r.dur):8.2f}ms")

# ---------------------------------------------------------------
# 6) Main thread long work — main app
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print(f"6) MAIN THREAD LONG SLICES (>16ms) — {main_app}")
print("=" * 72)
rows = q(f"""
  SELECT s.ts, s.dur, s.name, s.depth
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{main_app}' AND t.is_main_thread = 1 AND s.dur > 16000000
  ORDER BY s.dur DESC LIMIT 60
""")
agg = defaultdict(lambda: [0, 0, 0])
for r in rows:
    a = agg[r.name]
    a[0] += 1
    a[1] += r.dur
    a[2] = max(a[2], r.dur)
print("  by slice name (from top long slices):")
for name, (c, tot, mx) in sorted(agg.items(), key=lambda x: -x[1][1])[:20]:
    print(f"    {name[:60]:60} n={c:3} tot={ms(tot):8.1f}ms max={ms(mx):7.2f}ms")
print("  top 20 events:")
for r in rows[:20]:
    print(f"    t={t_rel(r.ts):7.3f}s {ms(r.dur):8.2f}ms  {r.name[:70]}")

# ---------------------------------------------------------------
# 7) Main thread depth0 breakdown — main app
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print(f"7) MAIN THREAD TIME BY SLICE (depth=0) — {main_app}")
print("=" * 72)
for r in q(f"""
  SELECT s.name, COUNT(*) AS n, SUM(s.dur)/1e6 AS total_ms,
         AVG(s.dur)/1e6 AS avg_ms, MAX(s.dur)/1e6 AS max_ms
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{main_app}' AND t.is_main_thread = 1 AND s.depth = 0
  GROUP BY s.name ORDER BY total_ms DESC LIMIT 30
"""):
    print(f"  {r.name[:55]:55} n={r.n:5} tot={r.total_ms:9.1f}ms avg={r.avg_ms:7.2f} max={r.max_ms:8.2f}")

# ---------------------------------------------------------------
# 8) Thread scheduling — main app main thread
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print(f"8) MAIN THREAD SCHEDULING — {main_app}")
print("=" * 72)
for r in q(f"""
  SELECT state, io_wait, COUNT(*) AS n, SUM(dur)/1e6 AS total_ms,
         MAX(dur)/1e6 AS max_ms, AVG(dur)/1e6 AS avg_ms
  FROM thread_state ts
  JOIN thread t USING(utid)
  JOIN process p USING(upid)
  WHERE p.name = '{main_app}' AND t.is_main_thread = 1
  GROUP BY state, io_wait ORDER BY total_ms DESC
"""):
    print(f"  state={r.state:4} io={r.io_wait} n={r.n:6} tot={r.total_ms:10.1f}ms max={r.max_ms:8.2f}ms avg={r.avg_ms:6.3f}")

print("\n  longest non-running:")
for r in q(f"""
  SELECT ts, dur, state, io_wait, cpu, blocked_function
  FROM thread_state tstate
  JOIN thread t USING(utid)
  JOIN process p USING(upid)
  WHERE p.name = '{main_app}' AND t.is_main_thread = 1 AND state != 'Running'
  ORDER BY dur DESC LIMIT 15
"""):
    print(f"    t={t_rel(r.ts):7.3f}s {r.state:3} {ms(r.dur):8.2f}ms cpu={r.cpu} io={r.io_wait} fn={r.blocked_function}")

# ---------------------------------------------------------------
# 9) Binder / lock / IO / GC on main thread
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print(f"9) BLOCKING PATTERNS on main thread — {main_app}")
print("=" * 72)
for label, pat in [
    ("binder", "%binder%"),
    ("Lock contention", "%Lock contention%"),
    ("monitor contention", "%monitor contention%"),
    ("inflate", "%nflate%"),
    ("measure", "%easure%"),
    ("layout", "%ayout%"),
    ("DrawFrame", "%DrawFrame%"),
    ("dequeueBuffer", "%equeueBuffer%"),
    ("queueBuffer", "%ueueBuffer%"),
    ("nativePollOnce", "%ativePollOnce%"),
    ("GC", "%GC%"),
    ("JIT", "%JIT%"),
    ("SharedPref", "%haredPreference%"),
    ("SQLite", "%QLite%"),
    ("open", "%open%"),
    ("read", "%read%"),
    ("flush", "%lush%"),
]:
    for r in q(f"""
      SELECT COUNT(*) AS n, SUM(s.dur)/1e6 AS total_ms, MAX(s.dur)/1e6 AS max_ms
      FROM slice s
      JOIN thread_track tt ON s.track_id = tt.id
      JOIN thread t ON tt.utid = t.utid
      JOIN process p ON t.upid = p.upid
      WHERE p.name = '{main_app}' AND t.is_main_thread = 1
        AND s.name LIKE '{pat}'
    """):
        if r.n and (r.total_ms > 10 or r.max_ms > 16):
            print(f"  {label:22} n={r.n:5} tot={r.total_ms:9.1f}ms max={r.max_ms:8.2f}ms")

# ---------------------------------------------------------------
# 10) RenderThread
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print(f"10) RenderThread DrawFrame — {main_app}")
print("=" * 72)
rows = q(f"""
  SELECT s.ts, s.dur, s.name
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{main_app}' AND t.name = 'RenderThread'
    AND (s.name LIKE 'DrawFrame%' OR s.name LIKE 'drawFrame%')
""")
if rows:
    durs = [r.dur for r in rows]
    n = len(durs)
    print(f"  n={n} avg={sum(durs)/n/1e6:.2f}ms max={max(durs)/1e6:.2f}ms >16ms={sum(1 for d in durs if d>16e6)}")
    for r in sorted(rows, key=lambda x: x.dur, reverse=True)[:10]:
        print(f"    t={t_rel(r.ts):7.3f}s {ms(r.dur):8.2f}ms")

print("\n  threads by total slice time:")
for r in q(f"""
  SELECT t.name AS thread, t.tid, COUNT(*) AS n,
         SUM(s.dur)/1e6 AS total_ms, MAX(s.dur)/1e6 AS max_ms
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE p.name = '{main_app}'
  GROUP BY t.utid ORDER BY total_ms DESC LIMIT 15
"""):
    print(f"    {r.thread[:30]:30} tid={r.tid:6} n={r.n:6} tot={r.total_ms:9.1f}ms max={r.max_ms:8.2f}ms")

# ---------------------------------------------------------------
# 11) SurfaceFlinger / HWC
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("11) SurfaceFlinger / HWC long work")
print("=" * 72)
for r in q("""
  SELECT p.name AS proc, t.name AS thread, s.ts, s.dur, s.name AS slice
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE (p.name LIKE '%surfaceflinger%' OR p.name LIKE '%composer%' OR p.name LIKE '%SurfaceFlinger%')
    AND s.dur > 8000000
  ORDER BY s.dur DESC LIMIT 20
"""):
    print(f"  t={t_rel(r.ts):7.3f}s {(r.proc or '')[:25]:25} {r.thread[:18]:18} {ms(r.dur):8.2f}ms {r.slice[:40]}")

# SF jank via frame timeline
print("\n  SurfaceFlinger frame jank:")
for r in q("""
  SELECT jank_type, COUNT(*) AS n, AVG(dur)/1e6 AS avg_ms, MAX(dur)/1e6 AS max_ms
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
  WHERE p.name LIKE '%surfaceflinger%' OR p.name IS NULL
  GROUP BY jank_type ORDER BY n DESC
"""):
    print(f"    {r.jank_type:50} n={r.n:5} avg={r.avg_ms:7.2f} max={r.max_ms:7.2f}")

# ---------------------------------------------------------------
# 12) CPU freq
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("12) CPU frequency")
print("=" * 72)
for r in q("""
  SELECT cpu, COUNT(*) AS n, MIN(value)/1000 AS min_mhz, MAX(value)/1000 AS max_mhz, AVG(value)/1000 AS avg_mhz
  FROM counter c
  JOIN cpu_counter_track t ON c.track_id = t.id
  WHERE t.name = 'cpufreq'
  GROUP BY cpu ORDER BY cpu
"""):
    print(f"  cpu{r.cpu}: n={r.n} min={r.min_mhz:.0f} max={r.max_mhz:.0f} avg={r.avg_mhz:.0f} MHz")

# ---------------------------------------------------------------
# 13) Input events
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("13) Input-related slices")
print("=" * 72)
for r in q(f"""
  SELECT p.name AS proc, s.name, COUNT(*) AS n, AVG(s.dur)/1e6 AS avg_ms, MAX(s.dur)/1e6 AS max_ms
  FROM slice s
  JOIN thread_track tt ON s.track_id = tt.id
  JOIN thread t ON tt.utid = t.utid
  JOIN process p ON t.upid = p.upid
  WHERE (s.name LIKE '%nput%' OR s.name LIKE '%deliverInput%' OR s.name LIKE '%TouchEvent%'
         OR s.name LIKE '%MotionEvent%' OR s.name LIKE '%InputDispatch%')
  GROUP BY p.upid, s.name
  HAVING max_ms > 5 OR n > 5
  ORDER BY max_ms DESC LIMIT 25
"""):
    print(f"  {(r.proc or '?')[:25]:25} {r.name[:55]:55} n={r.n:4} avg={r.avg_ms:7.2f} max={r.max_ms:8.2f}")

# ---------------------------------------------------------------
# 14) present_type distribution for main app
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print(f"14) PRESENT TYPE / ON_TIME for {main_app}")
print("=" * 72)
for r in q(f"""
  SELECT present_type, on_time_finish, COUNT(*) AS n, AVG(dur)/1e6 AS avg_ms
  FROM actual_frame_timeline_slice a
  LEFT JOIN process p USING(upid)
  WHERE p.name = '{main_app}'
  GROUP BY present_type, on_time_finish ORDER BY n DESC
"""):
    print(f"  present={str(r.present_type):25} on_time={r.on_time_finish} n={r.n:5} avg={r.avg_ms:7.2f}ms")

# ---------------------------------------------------------------
# 15) Layer name breakdown for jank
# ---------------------------------------------------------------
print("\n" + "=" * 72)
print("15) JANK BY LAYER")
print("=" * 72)
for r in q("""
  SELECT layer_name, jank_type, COUNT(*) AS n, AVG(dur)/1e6 AS avg_ms, MAX(dur)/1e6 AS max_ms
  FROM actual_frame_timeline_slice
  WHERE jank_type IS NOT NULL AND jank_type != 'None'
  GROUP BY layer_name, jank_type ORDER BY n DESC LIMIT 30
"""):
    print(f"  {str(r.layer_name)[:45]:45} {str(r.jank_type)[:35]:35} n={r.n:4} avg={r.avg_ms:7.2f} max={r.max_ms:7.2f}")

print("\nDONE")
