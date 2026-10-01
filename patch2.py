import re
with open("build_alpine_rts_container_v2.py", "r") as f:
    content = f.read()

content = content.replace('subprocess.run(["mke2fs", "-d", str(mount_point), "-t", "ext4", str(output_path)], check=True)',
'subprocess.run(["mke2fs", "-F", "-d", str(mount_point), "-t", "ext4", str(output_path)], check=True)')

with open("build_alpine_rts_container_v2.py", "w") as f:
    f.write(content)
