from infi.pyutils.contexts import contextmanager
from infi.projector.plugins import CommandPlugin
from textwrap import dedent
from logging import getLogger

logger = getLogger(__name__)

USAGE = """
Usage:
    projector repository init [--mkdir] <project_name> <origin> <short_description> <long_description>
    projector repository clone <origin>

Options:
    repository init         Create a new project/git repository
    repository clone        Clone an exisiting project/git repository
    <project_name>          The name of the project in pyhton-module-style (object)
    <origin>                Remote repository url
    <short_description>     A one-line description
    <long_description>      A multi-line description
    --mkdir                 Init the repository in a new directory instead of the current directory
"""

def get_package_namespace(name):
    namespaces = []
    for item in name.split('.')[:-1]:
        namespaces.append('.'.join([namespaces[-1], item]) if namespaces else item)
    return namespaces

def generate_package_code():
    from uuid import uuid1
    return '{' + str(uuid1()) + '}'

def indent(text):
    return '\n'.join(['\t{}'.format(line) for line in text.splitlines()]).strip()

class RepositoryPlugin(CommandPlugin):
    def get_docopt_string(self):
        return USAGE

    def get_command_name(self):
        return 'repository'

    def parse_commandline_arguments(self, arguments):
        methods = [self.init, self.clone]
        [method] = [method for method in methods
                    if arguments.get(method.__name__)]
        self.arguments = arguments
        method()

    def get_project_name(self):
        return self.arguments.get("<project_name>")

    @contextmanager
    def _create_subdir_if_necessary(self):
        from infi.projector.helper.utils import chdir
        from os.path import exists, isdir, sep
        from os import makedirs
        if not self.arguments.get('--mkdir'):
            yield
            return
        dirname = self.arguments.get('<project_name>') or self.arguments.get('<origin>')
        dirname = (dirname if not dirname.endswith('.git') else dirname[0:-4]).split(sep)[-1]
        if exists(dirname) and isdir(dirname):
            logger.debug("{} already exists".format(dirname))
            raise SystemExit(1)
        makedirs(dirname)
        with chdir(dirname):
            yield

    def _exit_if_dotgit_exists(self):
        from os.path import exists
        if exists('.git'):
            logger.error("This directory is already a git repository")
            raise SystemExit(1)

    def git_init(self):
        from os.path import curdir
        from gitpy.repository import LocalRepository
        repository = LocalRepository(curdir)
        repository.init()
        repository.addRemote("origin", self.arguments.get('<origin>'))

    def gitflow_init(self):
        from gitflow.core import GitFlow
        gitflow = GitFlow()
        gitflow.init(force_defaults=True)

    def release_initial_version(self):
        from infi.projector.helper.utils import release_version_with_git_flow
        release_version_with_git_flow("v0")

    def add_initial_files(self):
        from os.path import basename
        from shutil import copy
        from .skeleton import get_files
        for src, dst in [(filepath, basename(filepath)) for filepath in get_files()]:
            copy(src, dst)

    def set_buildout_config(self):
        from infi.projector.helper.utils import open_buildout_configfile
        project_name = self.get_project_name()
        with open_buildout_configfile(write_on_exit=True) as buildout:
            buildout.set('project', 'name', project_name)
            buildout.set('project', 'namespace_packages', get_package_namespace(project_name))
            buildout.set('project', 'version_file',
                             '/'.join(['src'] + project_name.split('.') + ['__version__.py']))
            buildout.set('project', 'description', self.arguments.get("<short_description>"))
            buildout.set('project', 'long_description', indent(self.arguments.get("<long_description>")))
            buildout.set('project', 'upgrade_code', generate_package_code())
            buildout.set('project', 'product_name', project_name)

    def get_package_directories(self):
        from os.path import sep
        name = self.get_project_name()
        return [item.replace('.', sep) for item in get_package_namespace(name)] + [name.replace('.', sep)]

    def generate_src(self):
        from os import mkdir
        from os.path import join
        file_content = """__import__("pkg_resources").declare_namespace(__name__)\n"""
        mkdir('src')
        for dirname in self.get_package_directories():
            mkdir(join('src', dirname))
            with open(join('src', dirname, '__init__.py'), 'w') as file:
                file.write(file_content)

    def append_to_gitignore(self):
        project_name = self.get_project_name()
        with open('.gitignore', 'a') as fd:
            fd.write('\n' + '/'.join(['src'] + project_name.split('.') + ['__version__.py']) + '\n')

    def commit_all(self):
        from os import curdir
        from gitpy import LocalRepository
        repository = LocalRepository(curdir)
        repository.addAll()
        repository.commit("added all project files")

    def git_checkout_develop(self):
        from os import curdir
        from gitpy import LocalRepository
        repository = LocalRepository(curdir)
        repository.checkout("develop")

    def init(self):
        with self._create_subdir_if_necessary():
            self._exit_if_dotgit_exists()
            self.git_init()
            self.gitflow_init()
            self.release_initial_version()
            self.git_checkout_develop()
            self.add_initial_files()
            self.set_buildout_config()
            self.generate_src()
            self.append_to_gitignore()
            self.commit_all()

    def git_clone(self):
        from os import curdir
        from gitpy import LocalRepository
        repository = LocalRepository(curdir)
        repository.clone(self.arguments.get("<origin>"))

    def clone(self):
        self.arguments['--mkdir'] = True
        with self._create_subdir_if_necessary():
            self.git_clone()
            self.git_checkout_develop()
            self.gitflow_init()
