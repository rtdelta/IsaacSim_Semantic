from pathlib import Path
for path in Path('/opt/ros/jazzy/share/rviz_common').rglob('*.rviz'):
    value=path.read_text()
    if 'Window Geometry:' in value:print(str(path));print(value[value.index('Window Geometry:'):]);print(value[:1000])
