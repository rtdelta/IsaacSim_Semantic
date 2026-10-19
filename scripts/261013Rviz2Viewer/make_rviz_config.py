"""Generate RViz config without a YAML dependency or installed plugin."""
from pathlib import Path
import re

def write_config(path,topics):
    # Use the installed RViz dock arrangement so the 3D view has useful space.
    default=Path('/opt/ros/jazzy/share/rviz_common/default.rviz')
    state=re.search(r'^  QMainWindow State: (\S+)',default.read_text(),re.M) if default.is_file() else None
    sensors=''
    for index,topic in enumerate(topics):
        sensors+=f'''      - Class: rviz_default_plugins/PointCloud2
        Enabled: {str(index==0).lower()}
        Name: {topic.split('/')[-2]}
        Topic:
          Value: {topic}
          Reliability Policy: Reliable
          Durability Policy: Transient Local
          History Policy: Keep Last
          Depth: 2
        Style: Points
        Size (Pixels): 2
        Size (m): 0.01
        Decay Time: 0
        Position Transformer: XYZ
        Color Transformer: FlatColor
        Color: 70; 225; 240
        Queue Size: 2
'''
    content='''Panels:
  - Class: rviz_common/Displays
    Name: Displays
    Property Tree Widget:
      Expanded:
        - /LiDAR1
      Splitter Ratio: 0.5
    Help Height: 40
    Tree Height: 500
  - Class: rviz_common/Views
    Name: Views
    Splitter Ratio: 0.5
  - Class: rviz_common/Time
    Name: Time
Visualization Manager:
  Class: ""
  Tools:
    - Class: rviz_default_plugins/Interact
    - Class: rviz_default_plugins/MoveCamera
    - Class: rviz_default_plugins/Select
  Global Options:
    Background Color: 24; 31; 38
    Fixed Frame: world
    Frame Rate: 30
  Displays:
    - Class: rviz_default_plugins/Grid
      Enabled: true
      Name: Grid
      Cell Size: 1
      Plane Cell Count: 40
      Reference Frame: world
    - Class: rviz_default_plugins/MarkerArray
      Enabled: true
      Name: Excavator Mesh
      Topic:
        Value: /rviz_viewer/excavator
        Reliability Policy: Reliable
        Durability Policy: Transient Local
        History Policy: Keep Last
        Depth: 1
    - Class: rviz_default_plugins/TF
      Enabled: true
      Name: Sensor Frames
      Show Axes: true
      Show Arrows: false
      Show Names: false
      Marker Scale: 0.35
      Frame Timeout: 30
    - Class: rviz_common/Group
      Enabled: true
      Name: LiDAR
      Displays:
'''+sensors+'''  Views:
    Current:
      Class: rviz_default_plugins/Orbit
      Name: Current View
      Distance: 18
      Pitch: 0.5
      Yaw: 0.8
      Focal Point:
        X: 2
        Y: 1
        Z: 1.5
      Target Frame: world
Window Geometry:
  Width: 1280
  Height: 800
  Hide Left Dock: false
  Hide Right Dock: false
'''
    if state:content+='  QMainWindow State: '+state.group(1)+'\n'
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(content,encoding='utf-8')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('topics',nargs='+');a=p.parse_args();write_config(a.path,a.topics)
