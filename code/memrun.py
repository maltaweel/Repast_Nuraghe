"""Run a command, report wall time, peak RSS of the process tree (sum, sampled 0.5 s), largest single child
(getrusage), cgroup memory.current peak and OOM events before/after. Usage: memrun.py LOG -- cmd..."""
import os, resource, subprocess, sys, time
log = sys.argv[1]; cmd = sys.argv[sys.argv.index("--") + 1:]
def ev():
    return dict(l.split() for l in open("/sys/fs/cgroup/memory.events"))
def tree_rss(pid):
    kids = {}
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                st = open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()
                kids.setdefault(int(st[1]), []).append(int(p))
            except Exception:
                pass
    tot, pss, todo = 0, 0, [pid]
    while todo:
        q = todo.pop()
        try:
            for l in open(f"/proc/{q}/status"):
                if l.startswith("VmRSS:"):
                    tot += int(l.split()[1]); break
            for l in open(f"/proc/{q}/smaps_rollup"):
                if l.startswith("Pss:"):
                    pss += int(l.split()[1]); break
        except Exception:
            pass
        todo += kids.get(q, [])
    return tot // 1024, pss // 1024
e0 = ev(); t0 = time.time()
with open(log, "w") as fh:
    p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
    peak = ppss = cg = 0
    while p.poll() is None:
        r_, s_ = tree_rss(p.pid); peak = max(peak, r_); ppss = max(ppss, s_); cg = max(cg, int(open("/sys/fs/cgroup/memory.current").read()) // 1048576)
        time.sleep(0.5)
e1 = ev()
ru = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024
msg = (f"[memrun] exit {p.returncode}; wall {time.time() - t0:.1f} s; peak tree RSS {peak} MB; peak tree PSS {ppss} MB; largest child {ru} MB; "
       f"cgroup peak {cg} MB; oom_kill {e0['oom_kill']}->{e1['oom_kill']} oom {e0['oom']}->{e1['oom']} max {e0['max']}->{e1['max']}")
open(log, "a").write(msg + "\n"); print(msg)
sys.exit(p.returncode)
