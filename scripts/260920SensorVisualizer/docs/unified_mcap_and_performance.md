# 统一 MCAP 与性能监测（2026-09-22）

继续打开原来的 scene16，在 Script Editor 重新运行项目 `run_in_isaac.py`。按 Play Simulation → Start Recording → Stop Recording 操作；停止后会自动合包，等待面板出现 `Recording complete. Unified bag:`。新包在本轮目录的 `bag_unified/`，原 `bag/`、PNG 和 JSON 保留。

前后左右相机标识统一为 `front / back / left / right`，后方图像目录和 ROS 话题使用 `back`。兼容原场景 `FisheyeRear` 的安装路径与变换；历史 `rear` 文件夹不改名，合包时映射到 `back`。

查看本轮 `performance_reference.json` 可找到资源与耗时日志所在目录。`resources.jsonl` 是约每秒资源采样，`timings.jsonl` 是各阶段耗时和事件，`summary.json` 是统计汇总。当前版本提供监测，不自动改变画质、采样率或仿真倍率。

以下记录数据接口、离线补打包与回退细节。

# Unified camera + LiDAR MCAP

Run the existing `run_in_isaac.py` again after closing the previous project panel. Open scene16 as before. Camera IDs are `front`, `back`, `left`, `right`; existing USD `FisheyeRear` mounts are resolved as the `back` camera without changing their transforms. New surround-stage builds author `FisheyeBack`. Historical directories keep their original names; the packer maps legacy `rear` to `back`.

1. Play Simulation, then Start Recording.
2. Stop Recording closes camera files and the original ROS bag, then automatically starts a separate system-ROS packing process.
3. Wait for `Recording complete. Unified bag: .../bag_unified`. The original `bag/` and camera PNG/JSON files are retained.
4. `bag_unified/` is a ROS 2 bag directory containing MCAP and `metadata.yaml`. Use this directory with `ros2 bag info` or `ros2 bag play`.

Per camera the bag adds `/camera/<id>/image_raw/compressed` (`CompressedImage`, original RGB PNG), `/camera/<id>/camera_info` (`CameraInfo`), `/camera/<id>/pose` (`PoseStamped`, optical pose in world). `/tf` adds `swing_coordinate -> camera_<id>_optical` using saved per-frame mounting transforms. `/sensor_visualizer/camera_metadata` is a `std_msgs/String` JSON document with schema version, calibration provenance, exposure configuration, axis/time conventions and alias information.

Images are raw distorted OpenCV fisheye images, not rectified. CameraInfo uses equidistant D=[k1,k2,k3,k4], the original K, identity R and nominal monocular P=[K|0]. Consumers must apply the fisheye model; a pinhole-only Camera display does not represent this lens. Image, CameraInfo, camera pose and camera TF share the image acquisition simulation timestamp. Optical axes are X right/Y down/Z forward; quaternion order XYZW. Exposure metadata is the saved configuration, not a claim of per-frame measured exposure. Each original message and its recording timestamp are copied unchanged; image and LiDAR counts need not be identical.

The packer only consumes committed groups from `capture_index.jsonl`, validates metadata timestamps, calibration, PNG payloads and saved relative/world pose consistency, then reads the complete output back and checks per-topic serialized-message digests and counts. It keeps failed partial exports in a uniquely named `.pending_*` directory. Existing successful outputs are never overwritten. `unified_export_status.json`, `unified_export_report.json` and `unified_export.log` provide progress, verification and errors. A live export owns `unified_export.lock`; after an abnormal process death, confirm that its PID is no longer the packer before manually removing a stale lock. Normal failures release the lock and can be retried with Stop Recording.

To pack an older completed four-camera session separately:

```bash
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 /root/gpufree-data/semantic/scripts/260920SensorVisualizer/tools/pack_session_mcap.py /absolute/session/path
```

This first version packages after recording. It does not publish live camera ROS image topics and does not remove the existing synchronous PNG encoding cost during recording.

# Performance output

Monitoring starts when the project runtime is created. Logs live under `<output_directory>/_performance/<run>/`; each recorded session has `performance_reference.json` linking its monitor run. A run may cover multiple recording sessions. `timings.jsonl` records monotonic and UTC event times including recording boundaries, `resources.jsonl` samples resources about once a second, and `summary.json` provides counts, averages, maxima and P95 over the most recent 4096 samples per span. File writes are batched in a background thread; Linux resource sampling is an independent standard-library process using `/proc`, cgroup files and installed `nvidia-smi`.

Resources include tracked Isaac/recorder/packer process CPU cores, RSS, read/write rates, whole-device GPU/VRAM and cgroup CPU/memory limits. CPU 1.0 means one full core. GPU values are device-wide, not attribution to a particular sensor. Recorder executables may fork: only the tracked PID is reported, not an unverified sum over unrelated ROS processes. Kit heartbeat age helps detect a blocked main loop.

Timing spans include motion, camera pose matching/grouping, per-camera PNG encoding plus writes, manifest writes, explicit limiter waiting, recorder shutdown and export. Spans can be nested and must not be summed as exclusive time. GPU kernel time cannot be inferred from Python callback duration. Native Kit limiting can add wait beyond the explicit Python `pacing.wait`. The panel shows runtime wall time, active simulation advancement, playback RTF and saved camera groups. Paused intervals are excluded from playback RTF; the configured maximum remains 0.1.

No dependencies, system services, desktop configuration or USD source files are changed by this feature. Restore project files from `reports/unified_bag/before/` to revert overwritten files; newly added files are listed in `reports/unified_bag/deployment.json`.
