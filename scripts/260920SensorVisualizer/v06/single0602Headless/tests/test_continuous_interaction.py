import asyncio
from copy import deepcopy
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from single0602_headless.contracts import load_job
from single0602_headless.interaction_clock import NativeStepClock,NATIVE_TIME_BASE,LEGACY_TIME_BASE
from single0602_headless.interactive_runtime import InteractiveRuntime
from single0602_headless.keyboard_control import KeyboardControl
from single0602_headless.trajectory import Trajectory,TrajectoryRecorder
from test_contract_and_input import metadata,state


class ClockTests(unittest.TestCase):
    def test_native_steps_ignore_wall_clock_and_duplicate_callback(self):
        clock=NativeStepClock();clock.bind(40.)
        self.assertAlmostEqual(clock.advance(40.1,.1),.1)
        self.assertEqual(clock.advance(40.1,.1),0.)
        self.assertAlmostEqual(clock.advance(40.2,.1),.1)
        self.assertAlmostEqual(clock.elapsed,.2);self.assertEqual(clock.step_index,2)
        clock.bind(0.);self.assertEqual(clock.elapsed,0.)
        with self.assertRaises(RuntimeError):clock.advance(.2,.1)
        clock.bind(10.)
        with self.assertRaises(RuntimeError):clock.advance(9.,.1)

    def test_no_obsolete_rate_limit_and_invalid_rates_rejected(self):
        self.assertEqual(load_job()['max_real_time_factor'],1.)
        for value in (.5,1.,2.):
            self.assertEqual(load_job(overrides={'max_real_time_factor':value})['max_real_time_factor'],value)
        for value in (0,-1,True,float('nan'),float('inf')):
            with self.assertRaises(ValueError):load_job(overrides={'max_real_time_factor':value})

    def test_new_and_legacy_time_bases_keep_original_time_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            for index,basis in enumerate((LEGACY_TIME_BASE,NATIVE_TIME_BASE)):
                rec=TrajectoryRecorder(Path(directory)/str(index),dict(metadata(),time_base=basis))
                rec.append(state(100));rec.append(state(101,2));rec.close()
                trajectory=Trajectory.load(rec.directory)
                self.assertEqual(trajectory.duration,1.)
                self.assertEqual(trajectory.sample(.5)['position_world_m'][0],1.)
                self.assertEqual(trajectory.metadata['time_base'],basis)
        with self.assertRaises(ValueError):Trajectory([state(0)],dict(metadata(),time_base='unknown'))
        with self.assertRaises(ValueError):Trajectory([state(0)],dict(metadata(),time_base=NATIVE_TIME_BASE,time_basis_version=1))


def shell():
    r=InteractiveRuntime.__new__(InteractiveRuntime)
    r.closed=r.failed=r.busy=False;r.lifecycle='running';r.error=None
    r.clock=NativeStepClock();r.clock.bind(10.);r.time_s=0.
    r.timeline_state='playing';r.playing=True;r.binding_pending=False
    r.keyboard=KeyboardControl();r.native_keys=set();r.native=None;r.hot=None
    r.event=Mock();r.publish=Mock();r.endpoint=NS(result=Mock())
    r.run_wall_start=r.run_native_start=None;r.play_wall_s=r.play_native_s=0.
    r.recorder=None;r.drains=set();r.last_trajectory=None;r.trajectory_phase='idle';r.trajectory_error=None
    r.stats={'physics_steps':0,'max_step_ms':0.}
    r.scene=NS(motion=NS(ready=True,cancel_commands=Mock()),timeline=NS(is_playing=lambda:False,is_stopped=lambda:True))
    return r


class NativeStepTests(unittest.TestCase):
    def test_only_physics_callback_advances_motion_once(self):
        r=shell();r._sync_timeline=Mock();r._commit=Mock()
        r.scene.check_stage=Mock();r.scene.native_time=Mock(return_value=10.1)
        r.scene.motion.controller=NS(step=Mock());r.scene.motion.base_controller=NS(step=Mock())
        r.scene.motion._command_angles=Mock(return_value=[0.]);r.scene.motion._apply_controlled_base=Mock()
        r.keyboard.step=Mock(return_value=False)
        r._physics_post(.1,None);r._physics_post(.1,None)
        r.scene.native_time.return_value=10.2;r._physics_post(.1,None)
        self.assertFalse(r.failed);self.assertEqual(r.stats['physics_steps'],2)
        self.assertEqual(r.scene.motion._apply_controlled_base.call_count,2)
        self.assertEqual(r.scene.motion.controller.step.call_count,2)
        for call in r.scene.motion.controller.step.call_args_list:self.assertAlmostEqual(call.args[0],.1)
        self.assertAlmostEqual(r.time_s,.2)


class StopTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_stop_drains_last_valid_state_without_tensor_read(self):
        with tempfile.TemporaryDirectory() as directory:
            r=shell();r.recorder=TrajectoryRecorder(Path(directory)/'one',dict(metadata(),time_base=NATIVE_TIME_BASE))
            r.recorder.append(state(0));r.recorder.append(state(.5,2))
            r._read_state=Mock(side_effect=AssertionError('STOP must not read released tensors'))
            r._sync_timeline();tasks=set(r.drains);r._sync_timeline()
            self.assertEqual(r.drains,tasks);self.assertIsNone(r.recorder)
            self.assertEqual(r.lifecycle,'stopped');self.assertTrue(r.binding_pending)
            await asyncio.gather(*tasks)
            trajectory=Trajectory.load(r.last_trajectory)
            self.assertEqual(trajectory.metadata['end_reason'],'native_stop')
            self.assertEqual(trajectory.metadata['last_valid_seq'],1)
            self.assertEqual(len(trajectory.states),2);self.assertEqual(trajectory.states[-1]['position_world_m'][0],2)
            self.assertEqual(r.trajectory_phase,'complete');self.assertFalse(r.failed)
            r._read_state.assert_not_called();r.scene.motion.cancel_commands.assert_called_once()

    async def test_write_failure_cannot_be_reported_complete_on_normal_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            r=shell();r.recorder=TrajectoryRecorder(Path(directory)/'failed',metadata())
            r.recorder.append(state(0));r.recorder.error='simulated disk failure'
            r.log=NS(append=Mock());r.event=InteractiveRuntime.event.__get__(r)
            r.keyboard.notify=r.event
            r._sync_timeline();await asyncio.gather(*r.drains)
            self.assertEqual(r.trajectory_phase,'failed')
            self.assertIn('simulated disk failure',r.trajectory_error)
            with self.assertRaises(ValueError):Trajectory.load(r.last_trajectory)


if __name__=='__main__':unittest.main()
