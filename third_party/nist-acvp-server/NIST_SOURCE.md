# NIST ACVP-Server Source

- source repository: https://github.com/usnistgov/ACVP-Server
- source git commit: a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324
- upstream release/tag: v1.1.0.43
- source git describe: v1.1.0.43-4-ga7f283cd
- copied timestamp: 2026-08-09T05:16:57Z
- selection reason: latest official master commit as of 2026-08-09; includes v1.1.0.43 tr1 support and the post-release official fixture corrections.
- integration note: NIST code is copied into this repository; it is not a git submodule.

This directory vendors the NIST ACVP-Server Gen/Val code needed by the NCCU
ACVP Server integration. Re-run scripts/nist/copy_nist_genval.sh to refresh it
from a local NIST ACVP-Server checkout.
