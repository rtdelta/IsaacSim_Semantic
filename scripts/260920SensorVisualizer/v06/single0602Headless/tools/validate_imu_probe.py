"""Serialize native IMU probe samples to a separate MCAP and read them back."""
import json
from pathlib import Path
import sys
import uuid
import rosbag2_py
from rclpy.serialization import serialize_message,deserialize_message
from sensor_msgs.msg import Imu

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0602_headless.imu_interface import ros_imu_fields


def main():
    source=Path(sys.argv[1])
    samples=json.loads(source.read_text())['with_gravity'][-60:]
    assert samples and all(s['is_valid'] for s in samples)
    directory=source.parent/('imu_probe_export_'+uuid.uuid4().hex[:12])
    writer=rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(directory),storage_id='mcap'),rosbag2_py.ConverterOptions('cdr','cdr'))
    topic='/imu/official_imu/data'
    writer.create_topic(rosbag2_py.TopicMetadata(id=1,name=topic,type='sensor_msgs/msg/Imu',serialization_format='cdr'))
    stamps=[]
    for sample in samples:
        fields=ros_imu_fields(sample);message=Imu()
        message.header.frame_id=fields['frame_id']
        message.header.stamp.sec,message.header.stamp.nanosec=divmod(fields['stamp_ns'],10**9)
        if fields['orientation'] is not None:
            for axis,value in zip('xyzw',fields['orientation']):setattr(message.orientation,axis,value)
        for name in ('linear_acceleration','angular_velocity'):
            for axis,value in zip('xyz',fields[name]):setattr(getattr(message,name),axis,value)
        for name in ('orientation_covariance','linear_acceleration_covariance','angular_velocity_covariance'):
            setattr(message,name,fields[name])
        writer.write(topic,serialize_message(message),fields['stamp_ns']);stamps.append(fields['stamp_ns'])
    del writer
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(directory),storage_id='mcap'),rosbag2_py.ConverterOptions('cdr','cdr'))
    actual=[]
    while reader.has_next():
        name,data,t=reader.read_next();assert name==topic
        message=deserialize_message(data,Imu);sample=samples[len(actual)]
        assert message.header.frame_id==sample['frame_id']
        assert message.header.stamp.sec*10**9+message.header.stamp.nanosec==t==stamps[len(actual)]
        assert [getattr(message.linear_acceleration,n) for n in 'xyz']==sample['linear_acceleration_m_s2']
        assert [getattr(message.angular_velocity,n) for n in 'xyz']==sample['angular_velocity_rad_s']
        assert [getattr(message.orientation,n) for n in 'xyzw']==sample['orientation_xyzw']
        assert all(v==0 for v in message.orientation_covariance)
        actual.append(t)
    assert len(actual)==len(samples) and all(b>a for a,b in zip(actual,actual[1:]))
    result={'passed':True,'bag':str(directory),'samples':len(actual),'source_time_preserved':True,
            'read_gravity':samples[0]['read_gravity'],'source_model':samples[0]['source_model'],
            'formal_synchronization_tested':False}
    (source.parent/'imu_probe_export_summary.json').write_text(json.dumps(result,indent=2))
    print('IMU_VALIDATION_JSON='+json.dumps(result))


if __name__=='__main__':main()
