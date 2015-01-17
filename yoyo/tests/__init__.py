from functools import wraps
from tempfile import mkdtemp
from shutil import rmtree
import os.path
import re

dburi = "sqlite:///:memory:"


def with_migrations(*migrations):
    """
    Decorator taking a list of migrations. Creates a temporary directory writes
    each migration to a file (named '0.py', '1.py', '2.py' etc), calls the
    decorated function with the directory name as the first argument, and
    cleans up the temporary directory on exit.
    """

    def unindent(s):
        initial_indent = re.search(r'^([ \t]*)\S', s, re.M).group(1)
        return re.sub(r'(^|[\r\n]){0}'.format(re.escape(initial_indent)),
                      r'\1', s)

    def decorator(func):
        tmpdir = mkdtemp()
        for ix, code in enumerate(migrations):
            with open(os.path.join(tmpdir, '{0}.py'.format(ix)), 'w') as f:
                f.write(unindent(code).strip())

        @wraps(func)
        def decorated(*args, **kwargs):
            args = args + (tmpdir,)
            try:
                func(*args, **kwargs)
            finally:
                rmtree(tmpdir)

        return decorated
    return decorator
