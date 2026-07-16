#!/usr/bin/env python3
from __future__ import annotations

import sys

from run_test import main


if __name__ == "__main__":
    raise SystemExit(main(["--expect-mode", "keyGen", "--variant", "fail", *sys.argv[1:]]))
