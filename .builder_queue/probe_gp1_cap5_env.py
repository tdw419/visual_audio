import os
p = "/var/tmp/gp1/cap5/env_probe.txt"
with open(p, "w") as f:
    f.write("HOME=" + os.environ.get("HOME", "unset") + "\n")
    f.write("PWD=" + os.getcwd() + "\n")
    f.write("LANG=" + os.environ.get("LANG", "unset") + "\n")
os.chdir("/var/tmp/gp1")
with open(p, "a") as f:
    f.write("PWD_AFTER_CHDIR=" + os.getcwd() + "\n")
    f.write("FAKE=" + os.environ.get("GP1_FAKE_VAR", "unset") + "\n")
