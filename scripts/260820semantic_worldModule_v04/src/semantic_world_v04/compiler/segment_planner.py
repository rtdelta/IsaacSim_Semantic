"""Deterministic pure-Python planning for independent Runtime segments."""

from typing import Dict, List

from semantic_world_v04.core.models import JobSpec, SCHEMA_VERSION, SegmentSpec
from semantic_world_v04.core.progress import groups_per_frame


class SegmentPlanner:
    def plan(self, job_spec: JobSpec) -> List[SegmentSpec]:
        project = job_spec.project
        capture = project.capture
        if capture.frame_count <= 0 or capture.segment_frames <= 0:
            raise ValueError("frame_count and segment_frames must be positive")
        positioning, segment_size = self._strategy(job_spec)
        variant_ids = [
            variant.variant_id for variant in project.variants if variant.enabled
        ]
        per_frame = groups_per_frame(project)
        result: List[SegmentSpec] = []
        offset = 0
        while offset < capture.frame_count:
            count = min(segment_size, capture.frame_count - offset)
            start = capture.start_frame + offset
            index = len(result)
            result.append(
                SegmentSpec(
                    schema_version=SCHEMA_VERSION,
                    job_id=job_spec.job_id,
                    job_content_digest=job_spec.content_digest,
                    segment_id=f"segment_{index:06d}",
                    segment_index=index,
                    start_frame=start,
                    frame_count=count,
                    end_frame_exclusive=start + count,
                    expected_capture_groups=per_frame * count,
                    motion_positioning=positioning,
                    variant_ids=list(variant_ids),
                )
            )
            offset += count
        self.validate(job_spec, result)
        return result

    def plan_document(self, job_spec: JobSpec) -> Dict[str, object]:
        segments = self.plan(job_spec)
        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_spec.job_id,
            "job_content_digest": job_spec.content_digest,
            "segment_count": len(segments),
            "segments": [segment.to_dict() for segment in segments],
        }

    @staticmethod
    def validate(job_spec: JobSpec, segments: List[SegmentSpec]) -> None:
        capture = job_spec.project.capture
        expected_positioning, _ = SegmentPlanner._strategy(job_spec)
        expected_variants = [
            variant.variant_id
            for variant in job_spec.project.variants
            if variant.enabled
        ]
        expected_groups_per_frame = groups_per_frame(job_spec.project)
        if not segments:
            raise ValueError("segment plan must not be empty")
        expected_start = capture.start_frame
        total_frames = 0
        for expected_index, segment in enumerate(segments):
            if segment.job_id != job_spec.job_id:
                raise ValueError("segment job_id does not match JobSpec")
            if segment.job_content_digest != job_spec.content_digest:
                raise ValueError("segment digest does not match JobSpec")
            if segment.segment_index != expected_index:
                raise ValueError("segment indices must be contiguous")
            if segment.segment_id != f"segment_{expected_index:06d}":
                raise ValueError("segment_id does not match segment index")
            if segment.schema_version != SCHEMA_VERSION:
                raise ValueError("segment schema_version is unsupported")
            if segment.motion_positioning != expected_positioning:
                raise ValueError("segment motion_positioning differs from strategy")
            if segment.variant_ids != expected_variants:
                raise ValueError("segment variant_ids differ from JobSpec")
            if segment.start_frame != expected_start:
                raise ValueError("segment ranges contain a gap or overlap")
            if segment.frame_count <= 0:
                raise ValueError("segment frame_count must be positive")
            if segment.end_frame_exclusive != segment.start_frame + segment.frame_count:
                raise ValueError("segment end_frame_exclusive is inconsistent")
            if segment.expected_capture_groups != (
                expected_groups_per_frame * segment.frame_count
            ):
                raise ValueError("segment expected_capture_groups is inconsistent")
            expected_start = segment.end_frame_exclusive
            total_frames += segment.frame_count
        if total_frames != capture.frame_count:
            raise ValueError("segment plan does not cover the complete capture range")

    @staticmethod
    def _strategy(job_spec: JobSpec):
        project = job_spec.project
        strategy = project.execution.segmentation_strategy
        supports_seek = project.motion.plugin == "none" or bool(
            project.motion.supports_absolute_seek
        )
        if strategy == "single_worker":
            return "single_worker", project.capture.frame_count
        if strategy == "replay_from_zero":
            return "replay_from_zero", project.capture.segment_frames
        if strategy != "auto":
            raise ValueError(f"unknown segmentation strategy: {strategy}")
        from semantic_world_v04.plugins import build_default_registry

        registry = build_default_registry()
        requires_history = False
        for sensor in project.sensors:
            if not sensor.enabled:
                continue
            plugin = registry.sensor(sensor.plugin)
            capabilities = getattr(plugin, "capabilities", lambda: None)()
            if capabilities is not None and capabilities.requires_continuous_history:
                requires_history = True
                break
        if requires_history:
            return "replay_from_zero", project.capture.segment_frames
        if supports_seek:
            return "absolute_seek", project.capture.segment_frames
        return "single_worker", project.capture.frame_count
