#!/usr/bin/env python3
from __future__ import annotations

import sys

from run_test import main


if __name__ == "__main__":
    raise SystemExit(main(["--expect-mode", "encapDecap", "--variant", "pass", *sys.argv[1:]]))
