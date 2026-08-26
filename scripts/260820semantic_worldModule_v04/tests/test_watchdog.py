import unittest

from semantic_world_v04.core.models import ExecutionPolicy, SegmentStatus
from semantic_world_v04.supervisor.watchdog import SegmentWatchdog


class WatchdogTests(unittest.TestCase):
    def test_start_heartbeat_and_no_progress_timeouts_are_distinct(self) -> None:
        policy = ExecutionPolicy(
            segment_start_timeout_seconds=10,
            heartbeat_timeout_seconds=20,
            no_progress_timeout_seconds=30,
        )
        watchdog = SegmentWatchdog(policy, started_monotonic=100.0)
        starting = SegmentStatus(job_id="job", segment_id="segment", state="starting")
        decision = watchdog.observe(
            starting, now_monotonic=111.0, process_alive=True
        )
        self.assertEqual("segment_start_timeout", decision.failure_code)

        watchdog = SegmentWatchdog(policy, started_monotonic=100.0)
        running = SegmentStatus(job_id="job", segment_id="segment", state="running")
        decision = watchdog.observe(
            running,
            now_monotonic=121.0,
            process_alive=True,
            heartbeat_age_seconds=21.0,
        )
        self.assertEqual("heartbeat_timeout", decision.failure_code)

        watchdog = SegmentWatchdog(policy, started_monotonic=100.0)
        decision = watchdog.observe(
            running,
            now_monotonic=131.0,
            process_alive=True,
            heartbeat_age_seconds=1.0,
        )
        self.assertEqual("no_progress_timeout", decision.failure_code)

    def test_new_commit_resets_no_progress_clock(self) -> None:
        policy = ExecutionPolicy(no_progress_timeout_seconds=10)
        watchdog = SegmentWatchdog(policy, started_monotonic=0.0)
        running = SegmentStatus(
            job_id="job",
            segment_id="segment",
            state="running",
            capture_groups_current=1,
        )
        self.assertIsNone(
            watchdog.observe(
                running,
                now_monotonic=9.0,
                process_alive=True,
                heartbeat_age_seconds=1.0,
            )
        )
        self.assertIsNone(
            watchdog.observe(
                running,
                now_monotonic=18.0,
                process_alive=True,
                heartbeat_age_seconds=1.0,
            )
        )

    def test_completed_worker_that_does_not_exit_is_timed_out(self) -> None:
        policy = ExecutionPolicy(heartbeat_timeout_seconds=10)
        watchdog = SegmentWatchdog(policy, started_monotonic=0.0)
        completed = SegmentStatus(
            job_id="job", segment_id="segment", state="completed"
        )
        decision = watchdog.observe(
            completed,
            now_monotonic=20.0,
            process_alive=True,
            heartbeat_age_seconds=11.0,
        )
        self.assertEqual("segment_exit_timeout", decision.failure_code)


if __name__ == "__main__":
    unittest.main()
