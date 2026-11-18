"""Restore desktop directory ownership, or install inherited ACLs as the desktop user."""
import os
from pathlib import Path
import re
import subprocess

desktop = Path('/home/dev/Desktop')
if not desktop.is_dir():
    raise SystemExit(0)


# Bind mounts may have the same st_dev as HOME. Leave the mounted tree to its owner.
def mount_path(name):
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), name)

mounts = {mount_path(line.split()[4]) for line in Path('/proc/self/mountinfo').read_text().splitlines()}
paths = []
for path, dirs, _, fd in os.fwalk(desktop, follow_symlinks=False):
    if path in mounts:
        dirs.clear()
        continue
    info = os.fstat(fd)
    if os.getuid() == 0:
        if info.st_uid == 0:
            os.fchown(fd, 1100, 1100)
            os.fchmod(fd, (info.st_mode & 0o7777) | 0o700)
    elif info.st_uid == os.getuid():
        paths.append(path)
        if len(paths) == 32:
            subprocess.run(['setfacl', '-m', 'd:u:dev:rwx', '--', *paths])
            paths.clear()
if paths:
    subprocess.run(['setfacl', '-m', 'd:u:dev:rwx', '--', *paths])
