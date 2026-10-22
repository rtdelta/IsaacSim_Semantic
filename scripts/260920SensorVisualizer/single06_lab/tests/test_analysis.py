import sqlite3,tempfile,unittest
from pathlib import Path
from lab.analysis import align_anchors,interval_union,native_report

class EvidenceTests(unittest.TestCase):
    def test_overlapping_gpu_work_is_not_summed(self):
        self.assertEqual(interval_union([(0,10),(5,15),(20,21),(4,4)]),16)
    def test_clock_alignment_reports_jitter(self):
        r=align_anchors([(100,1005),(200,1105),(300,1210)])
        self.assertEqual(r['offset_ns'],905);self.assertEqual(r['residual_max_abs_ns'],5)
        self.assertFalse(align_anchors([])['available'])
    def test_missing_metrics_are_not_zero(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'n.sqlite';sqlite3.connect(path).close()
            r=native_report(path,[])
            self.assertEqual(r['gpu_metrics'],{});self.assertIn('gpu_metrics_unavailable',r)
    def test_native_activity_union_and_metric_catalog(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'n.sqlite';db=sqlite3.connect(path)
            db.executescript('''CREATE TABLE StringIds(id INT,value TEXT);
             CREATE TABLE NVTX_EVENTS(start INT,end INT,text TEXT,textId INT,globalTid INT);
             INSERT INTO NVTX_EVENTS VALUES(10,30,'SL06_WINDOW',NULL,1);
             INSERT INTO NVTX_EVENTS VALUES(10,11,'SL06_SYNC host_ns=110',NULL,1);
             CREATE TABLE VULKAN_WORKLOAD(start INT,end INT);INSERT INTO VULKAN_WORKLOAD VALUES(10,22);
             CREATE TABLE CUPTI_ACTIVITY_KIND_KERNEL(start INT,end INT);INSERT INTO CUPTI_ACTIVITY_KIND_KERNEL VALUES(18,28);
             CREATE TABLE GPU_METRICS(timestamp INT,typeId INT,metricId INT,value REAL);
             CREATE TABLE TARGET_INFO_GPU_METRICS(typeId INT,metricId INT,metricName TEXT);
             INSERT INTO TARGET_INFO_GPU_METRICS VALUES(1,0,'SM Active');
             INSERT INTO GPU_METRICS VALUES(12,1,0,50),(22,1,0,70);''')
            db.close();r=native_report(path,[])
            self.assertEqual(r['clock_alignment']['offset_ns'],100)
            self.assertEqual(next(iter(r['stages'].values()))['gpu_activity_union_s'],18/1e9)
            self.assertEqual(r['gpu_metrics']['SM Active']['mean'],60)
if __name__=='__main__':unittest.main()
