import os
from pathlib import Path
import sys
import tempfile

def update(path, line):
    key = line.split()[2]
    old = path.read_text() if path.exists() else ''
    lines = [entry for entry in old.splitlines() if key not in entry.split()]
    if not any(entry.strip() and not entry.lstrip().startswith('#') for entry in lines):
        raise RuntimeError('Refusing to remove the last operator SSH key.')
    fd, temporary = tempfile.mkstemp(prefix='authorized-keys-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write('\n'.join(lines + [line]) + '\n')
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

if __name__ == '__main__':
    update(Path.home() / '.ssh/authorized_keys', sys.stdin.read().strip())
