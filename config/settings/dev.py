from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
# Off in development: AxesStandaloneBackend rejects Client.login() (it has no
# request), which would break the test suite and the local login loop. The
# lockout behaviour is covered by a test that re-enables it explicitly.
AXES_ENABLED = False
