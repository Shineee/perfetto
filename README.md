# Perfetto Android Trace

录制 Android Perfetto/atrace 性能追踪的轻量工具集，基于官方 `record_android_trace` 脚本，附带 Windows 一键录制入口。

## 环境要求

- Python 3
- Android 设备已开启 **USB 调试**，并通过 `adb` 连接
- 首次运行时会自动下载对应平台的 `tracebox` 预编译二进制（需要联网）

确认设备已连接：

```bash
adb devices
```

## 快速开始（Windows）

双击或在命令行运行：

```bat
record_trace.bat
```

默认行为（见 `record_trace.config`）：

| 参数 | 值 |
|------|-----|
| 输出文件 | `trace_file.perfetto-trace` |
| 时长 | 20 秒 |
| 缓冲区 | 32 MB |
| Atrace 分类 | `sched freq view ss input` |
| App | 全部应用（`atrace_apps: "*"`） |
| Frame Timeline | 已开启（`android.surfaceflinger.frametimeline`） |

录制结束后会自动在浏览器打开 [ui.perfetto.dev](https://ui.perfetto.dev) 加载该 trace。

> Frame Timeline 不是 atrace 分类，无法用 `-t/-b/-a` 短参数开启，必须通过完整 Perfetto 配置中的 `android.surfaceflinger.frametimeline` 数据源启用。开启后可在 UI / trace_processor 中查看 `expected_frame_timeline_slice` / `actual_frame_timeline_slice` 以及 `jank_type` 等帧级指标（Android 12+）。

## 手动录制

使用与 `record_trace.bat` 相同的配置：

```bash
python record_android_trace -c record_trace.config -o trace_file.perfetto-trace
```

仅用短参数（**不含** Frame Timeline）：

```bash
python record_android_trace -o trace_file.perfetto-trace -t 20s -b 32mb -a * sched freq view ss input
```

### 常用参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `-o, --out` | 输出文件或目录 | `~/traces/` |
| `-t, --time` | 时长，如 `10s`、`5m`；`0s` 表示手动停止 | `0s`（直到停止） |
| `-b, --buffer` | 环形缓冲区大小，如 `32mb`、`1gb` | `32mb` |
| `-a, --app` | 应用包名；`-a *` 表示全部应用 | 无 |
| `-s, --serial` | 指定 ADB 设备序列号 | 自动 |
| `-n, --no-open` | 录制后不打开/不提供 trace | — |
| `-c, --config` | 使用完整 Perfetto 配置文件 | — |
| `--list` | 列出可用 atrace 分类 | — |
| `--list-ftrace` | 列出可用 ftrace 事件 | — |

### 示例

录制 10 秒的调度与图形信息：

```bash
python record_android_trace -t 10s -b 32mb sched gfx wm -a*
```

指定设备并只追踪某个应用：

```bash
python record_android_trace -s <serial> -t 15s -a com.example.myapp sched freq
```

查看所有可用分类：

```bash
python record_android_trace --list
```

使用完整配置（可在 [ui.perfetto.dev/#!/record](https://ui.perfetto.dev/#!/record) 生成）：

```bash
python record_android_trace -c my_trace.config
```

长时间 trace 需使用完整配置并设置 `write_into_file = true`，参见 [Perfetto 长时追踪文档](https://perfetto.dev/docs/concepts/config#long-traces)。

## 查看 Trace

录制完成后：

1. 打开 [https://ui.perfetto.dev](https://ui.perfetto.dev)
2. 拖入 `trace_file.perfetto-trace`，或使用脚本自动打开的页面

## 文件说明

| 文件 | 说明 |
|------|------|
| `record_android_trace` | 官方 amalgamated Python 脚本（v58.2），负责录制与打开 trace |
| `record_trace.bat` | Windows 一键录制封装 |
| `record_trace.config` | 完整 Perfetto 配置（含 Frame Timeline 数据源） |
| `.gitignore` | 忽略本地 trace 输出与 `.mimocode/` |

> `record_android_trace` 由 Perfetto 官方 `tools/gen_amalgamated_python_tools` 自动生成，请勿手工编辑。

## License

Apache License 2.0（见脚本内版权声明，著作权归 Android Open Source Project）。
