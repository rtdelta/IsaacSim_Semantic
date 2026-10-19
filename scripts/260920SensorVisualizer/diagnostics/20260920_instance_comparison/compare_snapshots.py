"""Compare local read-only snapshots; does not connect to either instance."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def compare_files(a,b):
    result = {"identical":0,"different":[],"old_only":[],"new_only":[],"missing_both":[]}
    for path in sorted(set(a)|set(b)):
        old,new = a.get(path,{}),b.get(path,{})
        old_ok,new_ok = "kind" in old, "kind" in new
        if not old_ok and not new_ok:
            result["missing_both"].append(path)
        elif not old_ok:
            result["new_only"].append(path)
        elif not new_ok:
            result["old_only"].append(path)
        elif old.get("kind") == new.get("kind") and old.get("sha256") == new.get("sha256") and old.get("target") == new.get("target") and old.get("mode") == new.get("mode"):
            result["identical"] += 1
        else:
            result["different"].append({"path":path,"old":old,"new":new})
    return result

def main():
    old = json.loads((ROOT/"old_snapshot.json").read_bytes())
    new = json.loads((ROOT/"new_snapshot.json").read_bytes())
    packages = {"identical":0,"different":[],"old_only":{},"new_only":{}}
    for name in sorted(set(old["packages"])|set(new["packages"])):
        a,b = old["packages"].get(name),new["packages"].get(name)
        if a is None:packages["new_only"][name] = b
        elif b is None:packages["old_only"][name] = a
        elif a==b:packages["identical"] += 1
        else:packages["different"].append({"name":name,"old":a,"new":b})
    result = {"collected_at":{"old":old["collected_at_utc"],"new":new["collected_at_utc"]},
              "baselines":{"old":old["baseline"],"new":new["baseline"]},"packages":packages}
    for key in ("package_files","desktop_venv","config_files"):
        result[key] = compare_files(old[key],new[key])
    result["package_integrity"] = {}
    for label,snapshot in (("old",old),("new",new)):
        files = snapshot["package_files"]
        result["package_integrity"][label] = {
            "matched":sum(r.get("md5")==r["expected_md5"] for r in files.values()),
            "mismatched":[p for p,r in files.items() if "md5" in r and r["md5"]!=r["expected_md5"]],
            "unavailable":[p for p,r in files.items() if "md5" not in r]}
    result["runtime"] = {}
    for label,snapshot in (("old",old),("new",new)):
        processes = snapshot["processes"]
        wanted = ("gpufree","Xorg","xfce","selkies","libproc","polkitdl","nvidian-smi","dpkg-triggers")
        important = [r for r in processes if any(x in r["comm"] or x in r["exe"] for x in wanted)]
        # Process races can also produce a PID listing difference; names distinguish relevant cases.
        hidden = [r for r in processes if r["pid"] not in snapshot["visible_proc_pids"]]
        result["runtime"][label] = {
            "important_processes":important,"not_in_normal_proc_list":hidden,
            "top_cpu":sorted(processes,key=lambda x:x.get("cpu_cores_sample") or 0,reverse=True)[:8],
            "listener_ports":sorted({x["port"] for x in snapshot["tcp_listeners"]}),
            "memory_events":snapshot["memory_events"],"memory_current":snapshot["memory_current"]}
    result["read_comparisons"] = {"old":old["read_comparisons"],"new":new["read_comparisons"]}
    (ROOT/"comparison.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    compact = {"collected_at":result["collected_at"],
               "packages":{"identical":packages["identical"],"different":packages["different"],
                           "old_only":list(packages["old_only"]),"new_only":list(packages["new_only"])}}
    for key in ("package_files","desktop_venv","config_files"):
        v = result[key]
        compact[key] = {"identical":v["identical"],"different":[x["path"] for x in v["different"]],
                        "old_only_count":len(v["old_only"]),"new_only_count":len(v["new_only"]),
                        "missing_both_count":len(v["missing_both"])}
    compact["package_integrity"] = {label:{"matched":v["matched"],"mismatched":len(v["mismatched"]),
        "unavailable":len(v["unavailable"])} for label,v in result["package_integrity"].items()}
    print(json.dumps(compact,ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
