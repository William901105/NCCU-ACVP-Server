# Local NIST compatibility patches

The vendored oracle is based on the official NIST ACVP-Server commit
`a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324`
(`v1.1.0.43-4-ga7f283cd`, committed 2026-07-31). The current official
`usnistgov/ACVP-Server` `master` was rechecked on 2026-08-09 and still contained
the defect below.

This is not an unmodified official NIST GenVal source tree.

## ML-KEM FIPS203-tr1 decapsulationKeyCheck key format

- Patch: `scripts/nist/patches/a7f283cd-mlkem-tr1-decap-keycheck-keyformat.patch`
- SHA-256: `d421d216a21d0ea38a596342dee6a4144598f33fd40b7b58d4a5916203573ade`
- Upstream file: `gen-val/src/generation/src/NIST.CVP.ACVTS.Libraries.Generation/ML-KEM/FIPS203/tr1/EncapDecap/TestGroupGeneratorKeyCheckVal.cs`
- Local change: assign `KeyFormat = PrivateKeyFormat.Expanded` to generated
  `decapsulationKeyCheck` groups.

Without the assignment, the enum defaults to `PrivateKeyFormat.None`. The
prompt projection consequently omits both the expanded `dk` and seed-form
`d`/`z`, leaving only `tcId` in each test. The patch selects the expanded form,
matching the current ML-KEM ACVP test-case requirement and NIST's corrected
checked-in tr1 prompt fixture. No enum ordering, projection resolver, expected
result, IUT, or validation behavior is changed. The patch also adds a focused
NIST generation-library unit test which constructs this group and asserts
`KeyFormat == Expanded`.

`scripts/nist/copy_nist_genval.sh` verifies the official base SHA and the patch
hash before copying, then applies this patch. `scripts/nist/build_nist_genval.sh`
verifies the base manifest, patch hash, and patched source assignment before
publishing GenValApp and Orleans ServerHost.
