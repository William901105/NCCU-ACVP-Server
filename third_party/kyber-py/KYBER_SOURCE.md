# kyber-py Source

- source repository: https://github.com/GiacomoPope/kyber-py
- source git commit: 897923667b2fa80afcf910fc8c1825dddf54a97d
- copied timestamp: 2026-07-16T00:00:00Z
- license: MIT (see LICENSE)
- integration note: kyber-py is copied into this repository; it is not a git
  submodule. The upstream `assets/` directory (README images) is omitted.

This directory vendors GiacomoPope/kyber-py, a pure-Python ML-KEM (FIPS 203)
implementation. It is used only by the `IUT-tests/mlkem-native/` external
implementation-under-test harness to derive ACVP response vectors from prompt
vectors. It is not part of the server runtime and is never imported by the
production backend.

To refresh: re-clone the upstream repository at the desired commit and copy the
tree (excluding `.git` and `assets/`) over this directory.
