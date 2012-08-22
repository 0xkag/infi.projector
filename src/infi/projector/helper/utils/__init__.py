
from contextlib import contextmanager
from logging import getLogger

logger = getLogger(__name__)

BUILDOUT_PARAMETERS = ['-s']

def _chdir_and_log(path):
    from os import chdir
    chdir(path)
    logger.debug("Changed directory to {!r}".format(path))

@contextmanager
def chdir(path):
    from os.path import abspath
    from os import curdir
    path = abspath(path)
    current_dir = abspath(curdir)
    _chdir_and_log(path)
    try:
        yield
    finally:
        _chdir_and_log(current_dir)

@contextmanager
def open_buildout_configfile(filepath="buildout.cfg"):
    from ConfigParser import ConfigParser
    parser = ConfigParser()
    parser.read(filepath)
    try:
        yield parser
    finally:
        with open(filepath, 'w') as fd:
            parser.write(fd)

def is_running_inside_virtualenv():
    import sys
    return hasattr(sys, 'real_prefix')

def parse_args(commandline_or_args):
    return commandline_or_args if isinstance(commandline_or_args, list) else commandline_or_args.split()

def execute_assert_success(args):
    from infi import execute
    logger.info("Executing {}".format(' '.join(args)))
    execute.execute_assert_success(args)

def _get_executable_from_shebang_line():
    # The executable wrapper in distribute dynamically loads Python's DLL, which causes sys.executable to be the wrapper
    # and not the original python exeuctable. We have to find the real executable as Distribute does.
    from os import path
    import sys
    executable_script_py = sys.executable.replace(".exe", "-script.py")
    with open(executable_script_py) as fd:
        shebang_line = fd.readlines()[0].strip()
    executable_path = path.normpath(shebang_line[3:-1])
    return (executable_path + '.exe') if not executable_path.endswith('.exe') else executable_path

def execute_with_python(commandline_or_args):
    import sys
    from ..assertions import is_windows
    args = parse_args(commandline_or_args)
    executable = [sys.executable if not is_windows() else _get_executable_from_shebang_line()]
    if not is_running_inside_virtualenv():
        executable.append('-S')
    execute_assert_success(executable + args)

def execute_with_buildout(commandline_or_args):
    from os import name, path
    args = parse_args(commandline_or_args)
    execute_assert_success([path.join('bin', 'buildout{}'.format('.exe' if name == 'nt' else ''))] + \
                            BUILDOUT_PARAMETERS + args)

@contextmanager
def buildout_parameters_context(parameters):
    try:
        [BUILDOUT_PARAMETERS.append(param) for param in parameters if param not in BUILDOUT_PARAMETERS]
        yield
    finally:
        [BUILDOUT_PARAMETERS.remove(param) for param in parameters if param in BUILDOUT_PARAMETERS]

def release_version_with_git_flow(version_tag):
    from os import curdir
    from gitflow.core import GitFlow
    from gitpy import LocalRepository
    gitflow = GitFlow()
    gitflow.create("release", version_tag, base=None, fetch=False)
    gitflow.finish("release", version_tag, fetch=False, rebase=False, keep=False, force_delete=True,
                   tagging_info=dict(sign=False, message=version_tag))
    repository = LocalRepository(curdir)
    repository.checkout("develop")
    repository.commit("empty commit after version {}".format(version_tag), allowEmpty=True)
    repository.createTag("{}-develop".format(version_tag))

def git_checkout(branch_name_or_tag):
    from os import curdir
    from gitpy import LocalRepository
    try:
        LocalRepository(curdir).checkout(branch_name_or_tag)
    except Exception:
        logger.error("failed to checkout {}".format(branch_name_or_tag))
        raise SystemExit(1)
