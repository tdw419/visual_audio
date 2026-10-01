"""Diagnostic: does adding -p rss_timeline_plugin change the run outcome?
Writes output/probe_gh18_plugin_effect.txt"""
import subprocess
import os

env = dict(os.environ)
env["PATH"] = "/usr/bin:" + env.get("PATH", "")
env["PYTHONPATH"] = os.path.abspath(".builder_queue")
target = "tests/test_gh18_syscall_abi.py::test_gh18_bakes_and_abi_version_word"
base = ["/usr/bin/python3", "-m", "pytest", target,
        "-p", "no:cacheprovider", "-p", "no:randomly", "-v", "--tb=no", "-q"]

lines = []
r = subprocess.run(base, capture_output=True, text=True, env=env)
lines.append("PLAIN last: " + (r.stdout.strip().splitlines() or ["<none>"])[-1])
r2 = subprocess.run(base + ["-p", "rss_timeline_plugin"],
                    capture_output=True, text=True, env=env)
lines.append("PLUGIN last: " + (r2.stdout.strip().splitlines() or ["<none>"])[-1])
lines.append("PLUGIN rc: %d  tail-stderr: %s" % (r2.returncode, r2.stderr.strip().splitlines()[-1] if r2.stderr.strip() else "<empty>"))

out = open("output/probe_gh18_plugin_effect.txt", "w")
out.write("\n".join(lines) + "\n")
out.close()
print("\n".join(lines))
