#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib
import importlib.abc
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

SUPPORTED_MODES = {"keyGen", "encapDecap"}
SUPPORTED_IDENTITIES = {
    ("ML-KEM", "keyGen", "FIPS203"),
    ("ML-KEM", "encapDecap", "FIPS203"),
    ("ML-KEM", "encapDecap", "FIPS203-tr1"),
}
ENCAP_DECAP_FUNCTIONS = {
    "encapsulation",
    "decapsulation",
    "encapsulationKeyCheck",
    "decapsulationKeyCheck",
}
PARAMETER_OBJECTS = {
    "ML-KEM-512": "ML_KEM_512",
    "ML-KEM-768": "ML_KEM_768",
    "ML-KEM-1024": "ML_KEM_1024",
}


class IutRunnerError(RuntimeError):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate ML-KEM ACVP IUT response JSON from prompt JSON.",
    )
    parser.add_argument(
        "--prompt",
        default=str(SCRIPT_DIR / "prompt.json"),
        help="Path to ACVP prompt JSON. Default: ./prompt.json",
    )
    parser.add_argument(
        "--response-dir",
        default=str(SCRIPT_DIR / "response"),
        help="Directory for response_pass_<mode>.json and response_fail_<mode>.json.",
    )
    parser.add_argument(
        "--variant",
        choices=("pass", "fail", "both"),
        default="both",
        help="Which response fixture to write.",
    )
    parser.add_argument(
        "--expect-mode",
        choices=tuple(sorted(SUPPORTED_MODES)),
        help="Fail if the prompt mode does not match this value.",
    )
    parser.add_argument(
        "--kyber-py-src",
        default=os.environ.get("KYBER_PY_SRC"),
        help=(
            "Optional path to a GiacomoPope/kyber-py checkout or its src/ "
            "directory. Used when the package is not installed."
        ),
    )
    args = parser.parse_args(argv)

    try:
        prompt_path = Path(args.prompt)
        response_dir = Path(args.response_dir)
        prompt = _read_json(prompt_path)
        vector_set = _acvp_body(prompt)
        algorithm = _required_string(vector_set, "algorithm", "$.algorithm")
        mode = _required_string(vector_set, "mode", "$.mode")
        revision = _required_string(vector_set, "revision", "$.revision")
        _require_supported_identity(algorithm, mode, revision)
        if args.expect_mode and mode != args.expect_mode:
            raise IutRunnerError(
                f"prompt mode {mode!r} does not match expected mode {args.expect_mode!r}"
            )

        response_dir.mkdir(parents=True, exist_ok=True)
        crypto = _load_crypto(args.kyber_py_src)
        pass_response = _generate_response(vector_set, crypto)

        pass_output = response_dir / f"response_pass_{mode}.json"
        fail_output = response_dir / f"response_fail_{mode}.json"

        written = []
        if args.variant in {"pass", "both"}:
            written.append(_write_json(pass_output, pass_response))
        if args.variant in {"fail", "both"}:
            fail_response = copy.deepcopy(pass_response)
            _mutate_first_result(fail_response)
            written.append(_write_json(fail_output, fail_response))

        for path in written:
            print(path)
        return 0
    except Exception as exc:  # pragma: no cover - script-level failure path
        print(f"error: {exc}", file=sys.stderr)
        return 1


class CryptoBackend:
    def __init__(self, ml_kem_module: Any):
        self.ml_kem_module = ml_kem_module

    def parameter(self, parameter_set: str) -> Any:
        name = PARAMETER_OBJECTS.get(parameter_set)
        if name is None:
            raise IutRunnerError(f"unsupported parameterSet: {parameter_set!r}")
        return getattr(self.ml_kem_module, name)


def _load_crypto(kyber_src: Optional[str]) -> CryptoBackend:
    ml_kem_module = _import_kyber_py(kyber_src)
    if ml_kem_module is None:
        raise IutRunnerError(
            "No ML-KEM implementation is available. Clone "
            "https://github.com/GiacomoPope/kyber-py and pass "
            "--kyber-py-src /path/to/kyber-py/src (or set KYBER_PY_SRC)."
        )
    return CryptoBackend(ml_kem_module=ml_kem_module)


def _import_kyber_py(source_arg: Optional[str]) -> Any:
    try:
        return importlib.import_module("kyber_py.ml_kem")
    except Exception:
        _purge_modules("kyber_py")

    for candidate in _source_candidates(
        source_arg,
        "kyber_py",
        [
            REPO_ROOT / "third_party" / "kyber-py",
            REPO_ROOT / "third_party" / "kyber-py" / "src",
            SCRIPT_DIR / "kyber-py",
            SCRIPT_DIR / "kyber-py" / "src",
            Path("/tmp/kyber-py-source"),
            Path("/tmp/kyber-py-source/src"),
        ],
    ):
        _install_future_annotations_importer("kyber_py", candidate)
        try:
            return importlib.import_module("kyber_py.ml_kem")
        except Exception:
            _purge_modules("kyber_py")
            continue
    return None


def _source_candidates(
    explicit: Optional[str],
    package: str,
    defaults: Iterable[Path],
) -> Iterable[Path]:
    values = []
    if explicit:
        values.append(Path(explicit))
    values.extend(defaults)
    seen = set()
    for value in values:
        source = _normalize_source_path(value, package)
        if source is None:
            continue
        key = str(source.resolve())
        if key in seen:
            continue
        seen.add(key)
        yield source


def _normalize_source_path(path: Path, package: str) -> Optional[Path]:
    expanded = path.expanduser()
    if (expanded / package / "__init__.py").exists():
        return expanded
    if (expanded / "src" / package / "__init__.py").exists():
        return expanded / "src"
    return None


class _FutureAnnotationsLoader(importlib.abc.SourceLoader):
    def __init__(self, fullname: str, path: Path):
        self.fullname = fullname
        self.path = path

    def get_filename(self, fullname: str) -> str:
        return str(self.path)

    def get_data(self, path: str) -> bytes:
        data = Path(path).read_bytes()
        if path.endswith(".py") and b"from __future__ import annotations" not in data[:200]:
            data = b"from __future__ import annotations\n" + data
        return data


class _FutureAnnotationsFinder(importlib.abc.MetaPathFinder):
    def __init__(self, package: str, root: Path):
        self.package = package
        self.root = root

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname != self.package and not fullname.startswith(f"{self.package}."):
            return None
        parts = fullname.split(".")
        package_path = self.root.joinpath(*parts, "__init__.py")
        module_path = self.root.joinpath(*parts).with_suffix(".py")
        if package_path.exists():
            return importlib.util.spec_from_loader(
                fullname,
                _FutureAnnotationsLoader(fullname, package_path),
                origin=str(package_path),
                is_package=True,
            )
        if module_path.exists():
            return importlib.util.spec_from_loader(
                fullname,
                _FutureAnnotationsLoader(fullname, module_path),
                origin=str(module_path),
            )
        return None


def _install_future_annotations_importer(package: str, source_root: Path) -> None:
    for finder in list(sys.meta_path):
        if (
            isinstance(finder, _FutureAnnotationsFinder)
            and finder.package == package
            and finder.root == source_root
        ):
            return
    sys.meta_path.insert(0, _FutureAnnotationsFinder(package, source_root))


def _purge_modules(prefix: str) -> None:
    for name in list(sys.modules):
        if name == prefix or name.startswith(f"{prefix}."):
            sys.modules.pop(name, None)


def _generate_response(vector_set: Dict[str, Any], crypto: CryptoBackend) -> Dict[str, Any]:
    mode = _required_string(vector_set, "mode", "$.mode")
    revision = _required_string(vector_set, "revision", "$.revision")
    body: Dict[str, Any] = {
        "vsId": vector_set.get("vsId"),
        "algorithm": vector_set.get("algorithm", "ML-KEM"),
        "mode": mode,
        "revision": revision,
        "testGroups": [],
    }
    groups = vector_set.get("testGroups")
    if not isinstance(groups, list):
        raise IutRunnerError("$.testGroups must be an array")
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise IutRunnerError(f"$.testGroups[{group_index}] must be an object")
        parameter_set = _required_string(
            group, "parameterSet", f"$.testGroups[{group_index}].parameterSet"
        )
        function = group.get("function")
        tg_id = group.get("tgId")
        response_group = {"tgId": tg_id, "tests": []}
        tests = group.get("tests")
        if not isinstance(tests, list):
            raise IutRunnerError(f"$.testGroups[{group_index}].tests must be an array")
        for test_index, test in enumerate(tests):
            if not isinstance(test, dict):
                raise IutRunnerError(
                    f"$.testGroups[{group_index}].tests[{test_index}] must be an object"
                )
            response_group["tests"].append(
                _generate_test_response(mode, function, parameter_set, group, test, crypto)
            )
        body["testGroups"].append(response_group)
    return body


def _generate_test_response(
    mode: str,
    function: Optional[str],
    parameter_set: str,
    group: Dict[str, Any],
    test: Dict[str, Any],
    crypto: CryptoBackend,
) -> Dict[str, Any]:
    tc_id = test.get("tcId")
    ml_kem = crypto.parameter(parameter_set)

    if mode == "keyGen":
        d = _hex_bytes(_required_lookup(test, group, "d"), "d", expected_len=32)
        z = _hex_bytes(_required_lookup(test, group, "z"), "z", expected_len=32)
        ek, dk = ml_kem._keygen_internal(d, z)
        return {"tcId": tc_id, "ek": ek.hex().upper(), "dk": dk.hex().upper()}

    if mode == "encapDecap":
        if function not in ENCAP_DECAP_FUNCTIONS:
            raise IutRunnerError(f"unsupported encapDecap function: {function!r}")

        if function == "encapsulation":
            ek = _hex_bytes(_required_lookup(test, group, "ek"), "ek")
            m = _hex_bytes(_required_lookup(test, group, "m"), "m", expected_len=32)
            shared_key, ciphertext = ml_kem._encaps_internal(ek, m)
            return {
                "tcId": tc_id,
                "c": ciphertext.hex().upper(),
                "k": shared_key.hex().upper(),
            }

        if function == "decapsulation":
            ciphertext = _hex_bytes(_required_lookup(test, group, "c"), "c")
            # FIPS203-tr1 keyFormat "seed": the decapsulation key is carried as
            # separate d(32) and z(32) fields; expand them to the dk first.
            key_format = group.get("keyFormat", "expanded")
            if key_format == "seed" or ("d" in test and "z" in test and "dk" not in test):
                d = _hex_bytes(_required_lookup(test, group, "d"), "d", expected_len=32)
                z = _hex_bytes(_required_lookup(test, group, "z"), "z", expected_len=32)
                _ek, dk = ml_kem._keygen_internal(d, z)
            else:
                dk = _hex_bytes(_required_lookup(test, group, "dk"), "dk")
            shared_key = ml_kem._decaps_internal(dk, ciphertext)
            return {"tcId": tc_id, "k": shared_key.hex().upper()}

        if function == "encapsulationKeyCheck":
            ek = _hex_bytes(_required_lookup(test, group, "ek"), "ek")
            return {"tcId": tc_id, "testPassed": _encapsulation_key_valid(ml_kem, ek)}

        if function == "decapsulationKeyCheck":
            # The documented local GenVal patch emits expanded dk. Retain the
            # seed path for compatible external prompts, but never fabricate a
            # result when no private-key material is present.
            key_format = group.get("keyFormat", "expanded")
            if "dk" in test:
                dk = _hex_bytes(_required_lookup(test, group, "dk"), "dk")
            elif key_format == "seed" or ("d" in test and "z" in test):
                d = _hex_bytes(_required_lookup(test, group, "d"), "d", expected_len=32)
                z = _hex_bytes(_required_lookup(test, group, "z"), "z", expected_len=32)
                _ek, dk = ml_kem._keygen_internal(d, z)
            else:
                raise IutRunnerError(
                    "decapsulationKeyCheck prompt contains no dk or d+z; "
                    "a prompt-only IUT cannot produce a computable response"
                )
            return {"tcId": tc_id, "testPassed": _decapsulation_key_valid(ml_kem, dk)}

    raise IutRunnerError(f"unsupported ML-KEM mode: {mode!r}")


def _require_supported_identity(algorithm: str, mode: str, revision: str) -> None:
    identity = (algorithm, mode, revision)
    if identity not in SUPPORTED_IDENTITIES:
        raise IutRunnerError(
            "unsupported ML-KEM algorithm/mode/revision identity: "
            f"{algorithm}/{mode}/{revision}"
        )


def _encapsulation_key_valid(ml_kem: Any, ek: bytes) -> bool:
    """Type + modulus check: ek must decode canonically (Encode(Decode(ek)) == ek).

    kyber-py performs both checks inside ``_k_pke_encrypt`` and raises
    ``ValueError`` when either fails, so a successful trial encapsulation with
    dummy randomness proves the key is well-formed.
    """
    if len(ek) != 384 * ml_kem.k + 32:
        return False
    try:
        ml_kem._encaps_internal(ek, bytes(32))
    except ValueError:
        return False
    return True


def _decapsulation_key_valid(ml_kem: Any, dk: bytes) -> bool:
    """Type + hash check: dk length must be correct and the embedded H(ek) must
    match a fresh hash of the encapsulation key stored inside dk."""
    k = ml_kem.k
    if len(dk) != ml_kem._dk_size():
        return False
    ek_pke = dk[384 * k : 768 * k + 32]
    embedded_hash = dk[768 * k + 32 : 768 * k + 64]
    return ml_kem._H(ek_pke) == embedded_hash


def _mutate_first_result(payload: Any) -> None:
    body = _response_body(payload)
    test = _first_test(body)
    for field in ("ek", "c", "k", "dk"):
        value = test.get(field)
        if isinstance(value, str) and value:
            _mutate_hex_field(test, field)
            return
    if isinstance(test.get("testPassed"), bool):
        test["testPassed"] = not test["testPassed"]
        return
    raise IutRunnerError("first response test has no mutable output field")


def _mutate_hex_field(test: Dict[str, Any], field: str) -> None:
    value = test.get(field)
    if not isinstance(value, str) or not value:
        raise IutRunnerError(f"response test has no hex {field!r} field to mutate")
    replacement = "1" if value[0].upper() == "0" else "0"
    test[field] = f"{replacement}{value[1:]}"


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"prompt JSON not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> Path:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def _acvp_body(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        if "prompt" in payload and isinstance(payload["prompt"], dict):
            return payload["prompt"]
        return payload
    if isinstance(payload, list):
        for item in payload[1:]:
            if isinstance(item, dict) and "testGroups" in item:
                return item
    raise IutRunnerError("prompt payload does not contain an ACVP vector set body")


def _response_body(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        for item in payload[1:]:
            if isinstance(item, dict) and "testGroups" in item:
                return item
    raise IutRunnerError("response payload does not contain an ACVP response body")


def _first_test(body: Dict[str, Any]) -> Dict[str, Any]:
    groups = body.get("testGroups")
    if not isinstance(groups, list) or not groups:
        raise IutRunnerError("response body has no testGroups")
    tests = groups[0].get("tests")
    if not isinstance(tests, list) or not tests:
        raise IutRunnerError("response body has no tests")
    first = tests[0]
    if not isinstance(first, dict):
        raise IutRunnerError("first response test is not an object")
    return first


def _required_string(body: Dict[str, Any], field: str, path: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value:
        raise IutRunnerError(f"{path} must be a non-empty string")
    return value


def _required_lookup(test: Dict[str, Any], group: Dict[str, Any], field: str) -> Any:
    if field in test:
        return test[field]
    if field in group:
        return group[field]
    raise IutRunnerError(f"missing required field {field!r}")


def _hex_bytes(value: str, name: str, expected_len: Optional[int] = None) -> bytes:
    if not isinstance(value, str):
        raise IutRunnerError(f"{name} must be a hex string")
    if len(value) % 2:
        raise IutRunnerError(f"{name} must be even-length hex")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise IutRunnerError(f"{name} must contain only hex characters") from exc
    if expected_len is not None and len(decoded) != expected_len:
        raise IutRunnerError(f"{name} must be {expected_len} bytes")
    return decoded


if __name__ == "__main__":
    raise SystemExit(main())
