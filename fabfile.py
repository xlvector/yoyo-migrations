import re
from shutil import rmtree
from contextlib import contextmanager
from fabric.api import env, lcd, local, prompt, task
from tempfile import mkdtemp

env.shell = '/bin/sh -c'

#: Name of python module provided by this package
env.module_name = 'yoyo'

#: PyPI registered name
env.package_name = 'yoyo-migrations'

#: Where to host generated sphinx documentation
env.hosts = ['www.ollycope.com']
env.docsdir = 'www/ollycope.com/htdocs/software/%(package_name)s' % env

#: Regular expression to parse the version number out of a python source file
version_re = re.compile(b"^(__version__\s*=\s*)['\"]([^'\"]*)['\"]", re.M)

#: File in which we can find the version number
env.version_file = '{module_name}/__init__.py'.format(**env)


def scm_get_repo_root():
    return local("hg root", capture=True).strip()


def scm_get_repo_author():
    return local("hg showconfig ui.username", capture=True).strip()


def scm_clone_repo(src, dst):
    local("hg clone {} {}".format(src, dst))


def scm_record(message, *files):
    """
    Record a commit
    """
    local('hg commit -m "{message}" {files}'.format(files=' '.join(files),
                                                    message=message))


def scm_tag(version):
    with lcd(env.build_path):
        local("hg tag {version}".format(version=version))


def scm_pull(src, dst):
    """
    Pull commits/patches/tags from ``src`` to ``dst``
    """
    with lcd(dst):
        local("hg pull {}".format(src))


@contextmanager
def build():
    """
    Checkout and build a clean source distribution
    """
    if 'build_path' in env:
        with lcd(env.build_path):
            yield
        return

    env.author = scm_get_repo_author()
    env.dev_path = scm_get_repo_root()
    env.build_path = mkdtemp() + '/build'
    scm_clone_repo(env.dev_path, env.build_path)
    try:
        with lcd(env.build_path):
            local("python bootstrap.py")
            local("./bin/buildout")
            local("./bin/python setup.py sdist")
            _check_release()
            yield
    finally:
        rmtree(env.build_path)


def _check_changelog(version):
    """
    Check that a changelog entry exists for the given version
    """

    with open("%(build_path)s/CHANGELOG.rst" % env, 'r') as f:
        changes = f.read()

    # Check we've a changelog entry for the newly released version
    assert re.search(
        r'\b%s\b' % (re.escape(version),),
        changes,
        re.M
    ) is not None, "No changelog entry found for version %s" % (version,)


def _readversion():
    """
    Parse and return the current version number
    """
    with open("{build_path}/{version_file}".format(**env), 'r') as f:
        return version_re.search(f.read()).group(2)


def _updateversion(version, for_=''):
    """\
    Write the given version number and record a new commit
    """
    with open("{build_path}/{version_file}".format(**env), 'r') as f:
        s = f.read()

    s = version_re.sub(r"__version__ = '{}'".format(version), s)
    with open("{build_path}/{version_file}".format(**env), 'w') as f:
        f.write(s)

    if for_:
        for_ = ' for ' + for_

    with lcd(env.build_path):
        scm_record("Bumped version number" + for_, env.version_file)


@task()
def release():
    """
    Upload a new release to the PyPI.
    """
    with build():
        version = _readversion()
        assert version.endswith('dev')
        release_version = version.replace('dev', '')
        _check_changelog(release_version)
        _updateversion(release_version, 'release')
        scm_tag(release_version)

        local("cd %(build_path)s && ./bin/python setup.py sdist upload" % env)

        _updateversion(
            prompt("New development version number?",
                   default=_increment_version(release_version) + 'dev'), 'dev')
        scm_pull(env.build_path, env.dev_path)


def _check_release():
    """
    Check that the tests run and that the source dist can be installed cleanly
    in a virtualenv
    """
    with lcd(env.build_path):
        local("tox")
        try:
            local("virtualenv test_virtualenv")
            local("./test_virtualenv/bin/pip install ./dist/*.tar.gz" % env)
            local("./test_virtualenv/bin/python -c'import %s'" %
                  env.module_name)
        finally:
            local("rm -rf test_virtualenv")


def _increment_version(version):
    """
    Increment the least significant part of a version number string.

        >>> _increment_version("1.0.0")
        '1.0.1'
    """
    version = map(int, version.split('.'))
    version = version[:-1] + [version[-1] + 1]
    version = '.'.join(map(str, version))
    return version
