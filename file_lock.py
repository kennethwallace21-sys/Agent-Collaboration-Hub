"""Small fcntl.flock-compatible advisory mutex for POSIX and Windows."""
from __future__ import annotations

import os
import time

if os.name != "nt":
    from fcntl import LOCK_EX, LOCK_NB, LOCK_SH, LOCK_UN, flock
else:
    import errno
    import msvcrt

    LOCK_SH, LOCK_EX, LOCK_NB, LOCK_UN = 1, 2, 4, 8

    def flock(fd: int, operation: int) -> None:
        fd = fd if isinstance(fd, int) else fd.fileno()
        position = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            while True:
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    mode = msvcrt.LK_UNLCK if operation & LOCK_UN else msvcrt.LK_NBLCK
                    msvcrt.locking(fd, mode, 1)
                    return
                except OSError as error:
                    if operation & (LOCK_NB | LOCK_UN) or error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.05)
        finally:
            os.lseek(fd, position, os.SEEK_SET)
