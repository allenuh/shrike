"""Never let logging's fallback echo arbitrary messages/exceptions after stream failure."""

import logging
import sys
from contextlib import suppress


class SafeStderrHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        with suppress(OSError, ValueError, TypeError):
            sys.stderr.write(self.format(record) + "\n")
            sys.stderr.flush()
