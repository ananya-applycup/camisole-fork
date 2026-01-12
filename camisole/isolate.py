# This file is part of Camisole.
#
# Copyright (c) 2016 Antoine Pietri <antoine.pietri@prologin.org>
# Copyright (c) 2016 Association Prologin <info@prologin.org>
#
# Camisole is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Prologin-SADM is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Prologin-SADM.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import collections
import configparser
import ctypes
import itertools
import logging
import os
import pathlib
import subprocess
import tempfile
from contextlib import asynccontextmanager

from camisole.conf import conf
from camisole.utils import cached_classmethod


LIBC = ctypes.CDLL('libc.so.6')
LIBC.strsignal.restype = ctypes.c_char_p


# ============================================================================
# Box Lock Manager - Phase 2: Request-Level Locking
# ============================================================================

# Global registry of locks, one per box_id
_box_locks = {}
_box_locks_lock = asyncio.Lock()


class BoxBusyError(Exception):
    """Raised when box is busy (lock acquisition timeout)."""
    pass


class BoxUnavailableError(Exception):
    """Raised when box is broken/unavailable (init fails after retry)."""
    pass


async def get_box_lock(box_id: int):
    """
    Get or create an asyncio.Lock for a specific box_id.
    Thread-safe creation using _box_locks_lock.
    """
    async with _box_locks_lock:
        if box_id not in _box_locks:
            _box_locks[box_id] = asyncio.Lock()
        return _box_locks[box_id]


@asynccontextmanager
async def acquire_box(box_id: int, timeout: float = 5.0):
    """
    Acquire exclusive access to an isolate box for the duration of a request.
    
    This context manager:
    1. Acquires a per-box lock (with timeout)
    2. Cleans up any leftover state
    3. Initializes the box (with one retry on failure)
    4. Yields control for compile + execute
    5. Cleans up and releases lock (even on exception)
    
    Args:
        box_id: The isolate box ID to acquire (0 to num_boxes-1)
        timeout: Max seconds to wait for lock acquisition (default 5s)
    
    Raises:
        BoxBusyError: If lock cannot be acquired within timeout (409 Conflict)
        BoxUnavailableError: If box init fails after retry (503 Service Unavailable)
    
    Example:
        async with acquire_box(box_id=0):
            # Box 0 is exclusively yours, ready to use
            result = await lang.run()
    """
    box_lock = await get_box_lock(box_id)
    acquired = False  # FIX 1: Track if WE acquired the lock
    
    try:
        # Try to acquire lock with timeout
        await asyncio.wait_for(box_lock.acquire(), timeout=timeout)
        acquired = True
        
    except asyncio.TimeoutError:
        # Lock is held by another request - return 409 Conflict
        raise BoxBusyError(f"Box {box_id} is busy (timeout after {timeout}s)")
    
    try:
        cmd_base = ['isolate', '--box-id', str(box_id), '--cg']
        
        # FIX 2 & 4: Cleanup at START (ignore errors - box might not exist yet)
        cmd_cleanup = cmd_base + ['--cleanup']
        await communicate(cmd_cleanup)
        
        # FIX 2: Init box (must succeed, retry once if fails)
        cmd_init = cmd_base + ['--init']
        retcode, stdout, stderr = await communicate(cmd_init)
        
        if retcode != 0:
            # Init failed - retry once after cleanup
            logging.warning(f"Box {box_id} init failed, retrying: {stderr.decode()}")
            await communicate(cmd_cleanup)
            retcode, stdout, stderr = await communicate(cmd_init)
            
            if retcode != 0:
                # Still failed - box is unavailable, return 503
                raise BoxUnavailableError(
                    f"Box {box_id} init failed after retry: {stderr.decode()}")
        
        # Box is ready - yield control for compile + execute
        yield box_id
        
    finally:
        # FIX 4: Cleanup at END (always, even on exception)
        try:
            cmd_cleanup = ['isolate', '--box-id', str(box_id), '--cg', '--cleanup']
            await communicate(cmd_cleanup)
        except Exception as e:
            # Ignore cleanup errors in finally - we tried our best
            logging.warning(f"Box {box_id} cleanup failed in finally: {e}")
        
        # FIX 1: Release lock only if WE acquired it
        if acquired:
            box_lock.release()


# ============================================================================
# End of Box Lock Manager
# ============================================================================


def signal_message(signal: int) -> str:
    return LIBC.strsignal(signal).decode()


async def communicate(cmdline, data=None, **kwargs):
    logging.debug('Running %s', ' '.join(str(a) for a in cmdline))
    proc = await asyncio.create_subprocess_exec(
        *cmdline, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, **kwargs)
    stdout, stderr = await proc.communicate(data)
    retcode = await proc.wait()
    return retcode, stdout, stderr


CAMISOLE_OPTIONS = [
    'extra-time',
    'fsize',
    'mem',
    'processes',
    'quota',
    'stack',
    'time',
    'virt-mem',
    'wall-time',
]

CAMISOLE_TO_ISOLATE_OPTS = {
    # Memory is resident, if you want address space it's virtual memory
    'virt-mem': 'mem',
    'mem': 'cg-mem',
}

ISOLATE_TO_CAMISOLE_META = {
    # Consistency with the limit name
    # https://github.com/ioi/isolate/issues/20
    'time-wall': 'wall-time',
}


class IsolateInternalError(RuntimeError):
    def __init__(
        self,
        command,
        isolate_stdout,
        isolate_stderr,
        message="Isolate encountered an internal error."
    ):
        self.command = command
        self.isolate_stdout = isolate_stdout.decode(errors='replace').strip()
        self.isolate_stderr = isolate_stderr.decode(errors='replace').strip()

        message_list = [message]
        if self.isolate_stdout:
            message_list.append("Isolate output:\n    " + self.isolate_stdout)
        if self.isolate_stderr:
            message_list.append("Isolate error:\n    " + self.isolate_stderr)
        message_list.append("Command:\n    " + ' '.join(self.command))

        super().__init__('\n\n'.join(message_list))


class Isolator:
    def __init__(self, opts, allowed_dirs=None, box_id=None):
        self.opts = opts
        self.allowed_dirs = allowed_dirs if allowed_dirs is not None else []
        self.explicit_box_id = box_id
        self.path = None
        self.cmd_base = None

        # Directory containing all the info of the program
        self.stdout_file = '._stdout'
        self.stderr_file = '._stderr'
        self.meta_file = None

        self.stdout = None
        self.stderr = None
        self.meta = None
        self.info = None

        # Result of the isolate binary
        self.isolate_retcode = None
        self.isolate_stdout = None
        self.isolate_stderr = None

    async def __aenter__(self):
        if self.explicit_box_id is not None:
            # FIX 2 & 3: Use explicit box_id (init already done by acquire_box)
            # No need to call init or cleanup - acquire_box() handles that
            self.box_id = self.explicit_box_id
            self.cmd_base = ['isolate', '--box-id', str(self.box_id), '--cg']
            
            # FIX 3: Compute path deterministically from config (no isolate calls)
            self.path = self.isolate_conf.root / str(self.box_id) / 'box'
            
        else:
            # Auto-allocation: find an available box (backward compatibility)
            busy = {int(p.name) for p in self.isolate_conf.root.iterdir()}
            avail = set(range(self.isolate_conf.max_boxes)) - busy
            while avail:
                self.box_id = avail.pop()
                self.cmd_base = ['isolate', '--box-id', str(self.box_id), '--cg']
                cmd_init = self.cmd_base + ['--init']
                retcode, stdout, stderr = await communicate(cmd_init)
                if retcode == 2 and b"already exists" in stderr:
                    continue
                if retcode != 0:  # noqa
                    raise RuntimeError("{} returned code {}: “{}”".format(
                        cmd_init, retcode, stderr))
                break
            else:
                raise RuntimeError("No isolate box ID available.")
            self.path = pathlib.Path(stdout.strip().decode()) / 'box'
        
        self.meta_file = tempfile.NamedTemporaryFile(prefix='camisole-meta-')
        self.meta_file.__enter__()
        return self

    async def __aexit__(self, exc, value, tb):
        meta_defaults = {
            'cg-mem': 0,
            'cg-oom-killed': 0,
            'csw-forced': 0,
            'csw-voluntary': 0,
            'exitcode': 0,
            'exitsig': 0,
            'exitsig-message': None,
            'killed': False,
            'max-rss': 0,
            'message': None,
            'status': 'OK',
            'time': 0.0,
            'time-wall': 0.0,
        }
        with open(self.meta_file.name) as f:
            m = (line.strip() for line in f.readlines())
        m = dict(line.split(':', 1) for line in m if line)
        m = {k: (type(meta_defaults[k])(v)
                 if meta_defaults[k] is not None else v)
             for k, v in m.items()}
        if 'exitsig' in m:
            m['exitsig-message'] = signal_message(m['exitsig'])
        self.meta = {**meta_defaults, **m}
        verbose_status = {
            'OK': 'OK',
            'RE': 'RUNTIME_ERROR',
            'TO': 'TIMED_OUT',
            'SG': 'SIGNALED',
            'XX': 'INTERNAL_ERROR',
        }
        self.meta['status'] = verbose_status[self.meta['status']]

        if self.meta.get('cg-oom-killed'):
            self.meta['status'] = 'OUT_OF_MEMORY'

        for imeta, cmeta in ISOLATE_TO_CAMISOLE_META.items():
            if imeta in self.meta:
                self.meta[cmeta] = self.meta.pop(imeta)

        self.info = {
            'stdout': self.stdout,
            'stderr': self.stderr,
            'exitcode': self.isolate_retcode,
            'meta': self.meta
        }

        # FIX 5: Cleanup is a safety net for auto-allocated boxes only
        # Explicit boxes are cleaned by acquire_box() at request boundaries
        if self.explicit_box_id is None:
            cmd_cleanup = self.cmd_base + ['--cleanup']
            retcode, stdout, stderr = await communicate(cmd_cleanup)
            if retcode != 0:  # noqa
                raise RuntimeError("{} returned code {}: “{}”".format(
                    cmd_cleanup, retcode, stderr))

        self.meta_file.__exit__(exc, value, tb)

    async def run(self, cmdline, data=None, env=None,
                  merge_outputs=False, **kwargs):
        cmd_run = self.cmd_base[:]
        cmd_run += list(itertools.chain(
            *[('-d', d) for d in self.allowed_dirs]))

        for opt in CAMISOLE_OPTIONS:
            v = self.opts.get(opt)
            iopt = CAMISOLE_TO_ISOLATE_OPTS.get(opt, opt)

            if v is not None:
                cmd_run.append(f'--{iopt}={v!s}')
            # Unlike isolate, we don't limit the number of processes by default
            elif iopt == 'processes':
                cmd_run.append('-p')

        for e in ['PATH', 'LD_LIBRARY_PATH', 'LANG']:
            env_value = os.getenv(e)
            if env_value:
                cmd_run += ['--env', e + '=' + env_value]

        for key, value in (env or {}).items():
            cmd_run += ['--env={}={}'.format(key, value)]

        cmd_run += [
            '--meta={}'.format(self.meta_file.name),
            '--stdout={}'.format(self.stdout_file),
        ]

        if merge_outputs:
            cmd_run.append('--stderr-to-stdout')
        else:
            cmd_run.append('--stderr={}'.format(self.stderr_file))

        cmd_run += ['--run', '--']
        cmd_run += cmdline

        self.isolate_retcode, self.isolate_stdout, self.isolate_stderr = (
            await communicate(cmd_run, data=data, **kwargs))

        self.stdout = b''
        self.stderr = b''
        if self.isolate_retcode >= 2:  # Internal error
            raise IsolateInternalError(
                cmd_run,
                self.isolate_stdout,
                self.isolate_stderr
            )
        try:
            self.stdout = (self.path / self.stdout_file).read_bytes()
            if not merge_outputs:
                self.stderr = (self.path / self.stderr_file).read_bytes()
        except (IOError, PermissionError) as e:
            # Something went wrong, isolate was killed before changing the
            # permissions or unreadable stdout/stderr
            raise IsolateInternalError(
                cmd_run,
                self.isolate_stdout,
                self.isolate_stderr,
                message="Error while reading stdout/stderr: " + e.message,
            )

    @cached_classmethod
    def isolate_conf(cls):
        parser = configparser.ConfigParser()
        s = 'dummy'

        def dummy_section():
            yield f'[{s}]'
            with pathlib.Path(conf['isolate-conf']).expanduser().open() as f:
                yield from f

        parser.read_file(dummy_section())
        root = pathlib.Path(parser.get(s, 'box_root'))
        max_boxes = parser.getint(s, 'num_boxes')
        return (collections.namedtuple('conf', 'root, max_boxes')
                (root, max_boxes))
