# Copyright 2020 Artificial Intelligence Redefined <dev+cogment@ai-r.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import ast
import sys
import time
import logging
import threading
import traceback
import subprocess

from itertools import chain


def iteritems(d, *args, **kwargs):
    return iter(d.items(*args, **kwargs))


_logger = None


def _has_level_handler(logger):
    """Check if there is a handler in the logging chain that will handle
    the given logger's effective level.
    """
    level = logger.getEffectiveLevel()
    current = logger

    while current:
        if any(handler.level <= level for handler in current.handlers):
            return True

        if not current.propagate:
            break

        current = current.parent

    return False


def _log(type, message, *args, **kwargs):
    """Log a message to the 'werkzeug' logger.

    The logger is created the first time it is needed. If there is no
    level set, it is set to :data:`logging.INFO`. If there is no handler
    for the logger's effective level, a :class:`logging.StreamHandler`
    is added.
    """
    global _logger

    if _logger is None:
        _logger = logging.getLogger("reloader")

        if _logger.level == logging.NOTSET:
            _logger.setLevel(logging.INFO)

        if not _has_level_handler(_logger):
            _logger.addHandler(logging.StreamHandler())

    getattr(_logger, type)(message.rstrip(), *args, **kwargs)


def _iter_module_files():
    """This iterates over all relevant Python files.  It goes through all
    loaded files from modules, all files in folders of already loaded modules
    as well as all files reachable through a package.
    """
    # The list call is necessary on Python 3 in case the module
    # dictionary modifies during iteration.
    for module in list(sys.modules.values()):
        if module is None:
            continue
        filename = getattr(module, "__file__", None)
        if filename:
            if os.path.isdir(filename) and os.path.exists(
                    os.path.join(filename, "__init__.py")
            ):
                filename = os.path.join(filename, "__init__.py")

            old = None
            while not os.path.isfile(filename):
                old = filename
                filename = os.path.dirname(filename)
                if filename == old:
                    break
            else:
                if filename[-4:] in (".pyc", ".pyo"):
                    filename = filename[:-1]
                yield filename


def _find_observable_paths(extra_files=None):
    """Finds all paths that should be observed."""
    rv = set(
        os.path.dirname(os.path.abspath(x)) if os.path.isfile(x) else os.path.abspath(x)
        for x in sys.path
    )

    for filename in extra_files or ():
        rv.add(os.path.dirname(os.path.abspath(filename)))

    for module in list(sys.modules.values()):
        fn = getattr(module, "__file__", None)
        if fn is None:
            continue
        fn = os.path.abspath(fn)
        rv.add(os.path.dirname(fn))

    return _find_common_roots(rv)


def _get_args_for_reloading():
    """Determine how the script was executed, and return the args needed
    to execute it again in a new process.
    """
    rv = [sys.executable]
    py_script = sys.argv[0]
    args = sys.argv[1:]
    # Need to look at main module to determine how it was executed.
    __main__ = sys.modules["__main__"]

    # The value of __package__ indicates how Python was called. It may
    # not exist if a setuptools script is installed as an egg. It may be
    # set incorrectly for entry points created with pip on Windows.
    if getattr(__main__, "__package__", None) is None or (
            os.name == "nt" and
            __main__.__package__ == "" and
            not os.path.exists(py_script) and
            os.path.exists(py_script + ".exe")
    ):
        # Executed a file, like "python app.py".
        py_script = os.path.abspath(py_script)

        if os.name == "nt":
            # Windows entry points have ".exe" extension and should be
            # called directly.
            if not os.path.exists(py_script) and os.path.exists(py_script + ".exe"):
                py_script += ".exe"

            if (
                    os.path.splitext(sys.executable)[1] == ".exe" and
                    os.path.splitext(py_script)[1] == ".exe"
            ):
                rv.pop(0)

        rv.append(py_script)
    else:
        # Executed a module, like "python -m werkzeug.serving".
        if sys.argv[0] == "-m":
            # Flask works around previous behavior by putting
            # "-m flask" in sys.argv.
            # TODO remove this once Flask no longer misbehaves
            args = sys.argv
        else:
            if os.path.isfile(py_script):
                # Rewritten by Python from "-m script" to "/path/to/script.py".
                py_module = __main__.__package__
                name = os.path.splitext(os.path.basename(py_script))[0]

                if name != "__main__":
                    py_module += "." + name
            else:
                # Incorrectly rewritten by pydevd debugger from "-m script" to "script".
                py_module = py_script

            rv.extend(("-m", py_module.lstrip(".")))

    rv.extend(args)
    return rv


def _find_common_roots(paths):
    """Out of some paths it finds the common roots that need monitoring."""
    paths = [x.split(os.path.sep) for x in paths]
    root = {}
    for chunks in sorted(paths, key=len, reverse=True):
        node = root
        for chunk in chunks:
            node = node.setdefault(chunk, {})
        node.clear()

    rv = set()

    def _walk(node, path):
        for prefix, child in iteritems(node):
            _walk(child, path + (prefix,))
        if not node:
            rv.add("/".join(path))

    _walk(root, ())
    return rv


class ReloaderLoop(object):
    name = ""

    # monkeypatched by testsuite. wrapping with `staticmethod` is required in
    # case time.sleep has been replaced by a non-c function (e.g. by
    # `eventlet.monkey_patch`) before we get here
    _sleep = staticmethod(time.sleep)

    def __init__(self, extra_files=None, interval=1):
        self.extra_files = set(os.path.abspath(x) for x in extra_files or ())
        self.interval = interval

    def run(self):
        pass

    def restart_with_reloader(self):
        """Spawn a new Python interpreter with the same arguments as this one,
        but running the reloader thread.
        """
        while 1:
            _log("info", " * Restarting with %s" % self.name)
            args = _get_args_for_reloading()

            new_environ = os.environ.copy()

            new_environ["RUN_MAIN"] = "true"
            exit_code = subprocess.call(args, env=new_environ, close_fds=False)
            if exit_code != 3:
                return exit_code

    def trigger_reload(self, filename):
        _log("info", "Checking syntax before reloading. Filename: {}".format(filename))

        with open(filename) as source_file:
            try:
                ast.parse(source_file.read(), filename=filename)
            except SyntaxError:
                logging.error(f"{traceback.format_exc()}")
                return

        self.log_reload(filename)
        sys.exit(3)

    def log_reload(self, filename):
        filename = os.path.abspath(filename)
        _log("info", " * Detected change in %r, reloading" % filename)


class StatReloaderLoop(ReloaderLoop):
    name = "stat"

    def run(self):
        mtimes = {}
        while 1:
            for filename in chain(_iter_module_files(), self.extra_files):
                try:
                    mtime = os.stat(filename).st_mtime
                except OSError:
                    continue

                old_time = mtimes.get(filename)
                mtimes[filename] = mtime

                if old_time is None:
                    continue
                elif mtime > old_time:
                    self.trigger_reload(filename)

            self._sleep(self.interval)


def ensure_echo_on():
    """Ensure that echo mode is enabled. Some tools such as PDB disable
    it which causes usability issues after reload."""
    # tcgetattr will fail if stdin isn't a tty
    if not sys.stdin.isatty():
        return
    try:
        import termios
    except ImportError:
        return
    attributes = termios.tcgetattr(sys.stdin)
    if not attributes[3] & termios.ECHO:
        attributes[3] |= termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, attributes)


def run_with_reloader(main_func, *args):
    """Run the given function in an independent python interpreter."""
    import signal

    reloader = StatReloaderLoop()

    signal.signal(signal.SIGTERM, lambda _: sys.exit(0))
    try:
        if os.environ.get("RUN_MAIN") == "true":
            ensure_echo_on()
            t = threading.Thread(target=main_func, args=())
            t.setDaemon(True)
            t.start()
            reloader.run()
        else:
            sys.exit(reloader.restart_with_reloader())
    except KeyboardInterrupt:
        pass
