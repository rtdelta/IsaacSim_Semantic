"""Editor-only axes: SceneUI drawing, no USD meshes or sensor render products."""
import uuid
import numpy as np
from .reference_frames import quaternion_matrix


class FrameOverlay:
    def __init__(self, motion):
        self.motion = motion
        self.window = self.view = self.frame = None
        self.lines = []

    def show(self):
        from omni.ui import scene as sc
        from omni.kit.viewport.utility import get_active_viewport_window
        self.window = get_active_viewport_window()
        if self.window is None:
            raise RuntimeError('Open a viewport to display reference axes')
        self.frame = self.window.get_frame('LidarFrames_' + uuid.uuid4().hex)
        with self.frame:
            self.view = sc.SceneView()
        self.window.viewport_api.add_scene_view(self.view)
        with self.view.scene:
            for length, colors, width in (
                    (1.0, [(1.,.15,.15,1.),(.15,1.,.15,1.),(.15,.35,1.,1.)], 5),
                    (1.4, [(1.,.65,.65,1.),(.65,1.,.65,1.),(.65,.8,1.,1.)], 2)):
                self.lines.append((length, [sc.Line([0,0,0], [0,0,0], color=c, thickness=width) for c in colors]))
        self.update()

    def update(self):
        if not self.view or not self.motion.frame_snapshot:
            return
        row = self.motion.frame_snapshot
        origin = np.array(row['position'])
        for (length, axes), q in zip(self.lines, (row['root_xyzw'], row['xyzw'])):
            rotation = quaternion_matrix(q)
            for i, line in enumerate(axes):
                line.start = origin.tolist()
                line.end = (origin + length * rotation[:, i]).tolist()

    def close(self):
        if self.view:
            if self.window:
                self.window.viewport_api.remove_scene_view(self.view)
            self.view.scene.clear()
            self.view.destroy()
        if self.frame:
            self.frame.clear()
        self.view = self.window = self.frame = None
        self.lines.clear()
