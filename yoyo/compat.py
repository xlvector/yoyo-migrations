import sys


PY2 = sys.version_info[0] == 2

if PY2:
    ustr = unicode
else:
    ustr = str

if PY2:
    exec('def reraise(tp, value, tb):\n raise tp, value, tb')
else:
    def reraise(tp, value, tb):
        raise value.with_traceback(tb)


if PY2:
    exec('def exec_(code, globals_):\n '
         'exec code in globals_')
else:
    def exec_(code, globals_):
        exec(code, globals_)
