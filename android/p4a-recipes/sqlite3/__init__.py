"""Local sqlite3 recipe for the BLEConnect Android builds.

The upstream recipe builds sqlite's code-generation tools with the Android
toolchain. On a host where the NDK linker appears first in PATH, host tools fail
with ``--no-add-needed``; Tcl 9 also needs an explicit codegen shell. This local
recipe keeps those host-tool details out of the project build directory.
"""

import shutil
from multiprocessing import cpu_count
from pathlib import Path

import sh
from pythonforandroid.logger import shprint
from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class Sqlite3Recipe(Recipe):
    version = "3.50.4"
    url = "https://github.com/sqlite/sqlite/archive/refs/tags/version-{version}.tar.gz"
    built_libraries = {"libsqlite3.so": "."}

    def build_arch(self, arch):
        env = self.get_recipe_env(arch)
        build_dir = self.get_build_dir(arch.arch)
        tclsh = shutil.which("tclsh")
        if not tclsh:
            raise RuntimeError(
                "sqlite code generation needs tclsh; install the tcl package"
            )
        cc = shutil.which("cc") or shutil.which("gcc") or "cc"
        cc_dir = str(Path(cc).parent)

        config_args = {
            "--host={}".format(arch.command_prefix),
            "--prefix={}".format(build_dir),
            "--disable-tcl",
            "--with-tclsh={}".format(tclsh),
        }
        with current_directory(build_dir):
            configure = sh.Command("./configure")
            shprint(configure, *config_args, _env=env)
            shprint(
                sh.make,
                "-j",
                str(cpu_count()),
                "TCLSH_CMD={}".format(tclsh),
                "B.cc={} -B{} -g".format(cc, cc_dir),
                _env=env,
            )


recipe = Sqlite3Recipe()
