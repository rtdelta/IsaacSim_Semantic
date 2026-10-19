from pathlib import Path
here = Path(__file__).resolve().parent
s = (here/'download_unified_bag.py').read_text()
s = s.replace("here/'download_source.json'", "here/'render_source.json'")
s = s.replace("260707IsaacSIm/output').resolve()", "260707IsaacSIm/scripts/260920SensorVisualizer/reports/20260923_review/image_samples').resolve()")
s = s.replace('mcap-download-20260923', 'render-architecture-review-20260923')
s = s.replace('Download user-requested completed unified MCAP to local output', 'Read existing camera samples locally for user-requested blur diagnosis')
s = s.replace('download_manifest.json', 'sample_transfer_manifest.json')
(here/'download_render_samples.py').write_text(s, encoding='utf-8')
