from contextlib import contextmanager
from infi.projector.plugins import CommandPlugin
from infi.projector.helper import assertions
from textwrap import dedent
from logging import getLogger

logger = getLogger(__name__)

USAGE = """
Usage:
    projector build scripts [--clean] [--force-bootstrap] [--no-submodules] [--no-scripts] [--no-readline] [--use-isolated-python] [[--newest] | [--offline]]
    projector build relocate ([--absolute] | [--relative]) [--commit-changes]

Options:
    build scripts           use this command to generate setup.py and the console scripts
    build relocate          use this command to switch from relative and absolute paths in the console scripts
    --force-bootstrap       run bootstrap.py even if the buildout script already exists
    --no-submodules         do not clone git sub-modules defined in buildout.cfg
    --no-scripts            do not install the dependent packages, nor create the console scripts. just create setup.py
    --no-readline           do not install [py]readline support (where applicable)
    --use-isolated-python   do not use global system python in console scripts, use Infinidat's isolated python builds
    --newest                always check for new package verson on PyPI
    --offline               install packages only from download cache (no internet connection)
    --clean                 clean build-related files and directories before building
"""

class BuildPlugin(CommandPlugin):
    def get_docopt_string(self):
        return USAGE

    def get_command_name(self):
        return 'build'

    @assertions.requires_repository
    def parse_commandline_arguments(self, arguments):
        methods = [self.scripts, self.relocate]
        [method] = [method for method in methods
                    if arguments.get(method.__name__)]
        self.arguments = arguments
        method()

    def create_cache_directories(self):
        from infi.projector.helper.utils import open_buildout_configfile
        from os import makedirs
        from os.path import join, exists
        with open_buildout_configfile() as buildout:
            cachedir = buildout.get("buildout", "download-cache")
        cache_dist = join(cachedir, "dist")
        if not exists(cache_dist):
            makedirs(cache_dist)

    def bootstrap_if_necessary(self):
        from os.path import exists, join
        from infi.projector.helper.utils import execute_with_python
        from infi.projector.helper.assertions import is_executable_exists
        if not exists("bootstrap.py"):
            logger.error("bootsrap.py does not exist")
            raise SystemExit(1)
        if not is_executable_exists(join("bin", "buildout")) or self.arguments.get("--force-bootstrap", False):
            execute_with_python("bootstrap.py -d -t")

    def install_sections_by_recipe(self, recipe):
        from infi.projector.helper.utils import open_buildout_configfile, execute_with_buildout
        with open_buildout_configfile() as buildout:
            sections_to_install = [section for section in buildout.sections()
                                   if buildout.has_option(section, "recipe") and \
                                      buildout.get(section, "recipe") == recipe]
        if sections_to_install:
            execute_with_buildout("install {}".format(' '.join(sections_to_install)))

    def submodule_update(self):
        from infi.projector.helper.utils import buildout_parameters_context
        with buildout_parameters_context(['buildout:develop=']):
            self.install_sections_by_recipe("zerokspot.recipe.git")

    def create_setup_py(self):
        from infi.projector.helper.utils import buildout_parameters_context
        with buildout_parameters_context(['buildout:develop=']):
            self.install_sections_by_recipe("infi.recipe.template.version")

    def create_scripts(self):
        from infi.projector.helper.utils import open_buildout_configfile, execute_with_buildout
        from infi.projector.helper.utils import buildout_parameters_context
        from infi.projector.helper.assertions import is_executable_exists
        from os import path
        python = path.join('parts', 'python', 'bin', 'python')
        if self.arguments.get("--use-isolated-python", False):
            if self.arguments.get("--newest", False) or not is_executable_exists(python):
                execute_with_buildout("install python-distribution")
        with self.buildout_use_custom_python():
            self.install_sections_by_recipe("infi.vendata.console_scripts")

    def clean_build(self):
        from os.path import exists
        from os import remove
        from shutil import rmtree
        directories_to_clean = ['bin', 'eggs', 'develop-eggs']
        files_to_clean = ['setup.py']
        [remove(filename) for filename in files_to_clean if exists(filename)]
        [rmtree(dirname)  for dirname in directories_to_clean if exists(dirname)]

    @contextmanager
    def buildout_newest_or_offline_context(self):
        from infi.projector.helper.utils import buildout_parameters_context
        parameters = []
        if self.arguments.get('--newest'):
            parameters.append('-n')
        if self.arguments.get('--offline'):
            parameters.append('-o')
        with buildout_parameters_context(parameters):
            yield

    @contextmanager
    def buildout_use_custom_python(self):
        from infi.projector.helper.utils import execute_with_buildout, execute_with_python
        from infi.projector.helper.utils import buildout_parameters_context
        from infi.projector.helper.assertions import assert_buildout_executable_exists
        from infi.projector.helper.assertions import is_buildout_executable_using_isolated_python
        if self.arguments.get("--use-isolated-python", False):
            yield
            assert_buildout_executable_exists()
            if is_buildout_executable_using_isolated_python():
                with buildout_parameters_context(["buildout:python=buildout"]):
                    # We need to make sure bin/buildout doesn't use the inside isolated python
                    execute_with_python("bootstrap.py -d -t")
        else:
            with buildout_parameters_context(["buildout:python=buildout"]):
                # This is because most of our existing projects use python-distribution by default
                yield

    def get_readline_module(self):
        from platform import system
        modules = {"Darwin": 'readline',
                   "Windows": 'pyreadline'}
        return modules.get(system())

    def is_module_installed(self, module):
        from infi.execute import execute_assert_success, ExecutionError
        try:
            execute_assert_success("bin/python -c import {}".format(module).split())
        except ExecutionError:
            return False
        return True

    def install_readline(self):
        from platform import system
        from infi.execute import execute_assert_success
        module = self.get_readline_module()
        if not module or self.is_module_installed(module):
            return
        execute_assert_success("bin/easy_install {}".format(module).split())

    def scripts(self):
        from infi.projector.helper.utils import buildout_parameters_context
        if self.arguments.get("--clean", False):
            self.clean_build()
        self.create_cache_directories()
        self.bootstrap_if_necessary()
        with self.buildout_newest_or_offline_context():
            if not self.arguments.get("--no-submodules", False):
                self.submodule_update()
            if not self.arguments.get("--no-setup-py", False):
                self.create_setup_py()
            if not self.arguments.get("--no-scripts", False):
                self.create_scripts()
            if not self.arguments.get("--no-readline", False):
                self.install_readline()

    def relocate(self):
        from infi.projector.helper.utils import open_buildout_configfile
        from os import curdir
        from gitpy import LocalRepository
        relative_paths = self.arguments.get("--relative", False)
        with open_buildout_configfile() as buildout:
            buildout.set("buildout", "relative-paths", 'true' if relative_paths else 'false')
            relative_python = 'parts/python/bin/python'
            absolute_python = '${buildout:directory}/parts/python/bin/python'
            buildout.set("python-distribution", "executable", relative_python if relative_paths else absolute_python)
        if self.arguments.get("--commit-changes", False):
            repository = LocalRepository(curdir)
            repository.add("buildout.cfg")
            repository.commit("Changing shebang to {} paths".format("relative" if relative_paths else "absolute"))
        logger.info("Configuration changed. Run `projector build scripts [--use-isolated-python]`.")
