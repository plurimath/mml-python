"""Build the sibling generated Rust codec crate for this Python package."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys



def source_identity(source):
    return {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
        "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=source, text=True).strip(),
    }


def capture_runtime_notices(metadata, destination, source_roots=()):
    """Retain actual resolved-source notices separately from the model-source notices."""
    notices = destination / "runtime-licenses"
    records = []
    for package in metadata["packages"]:
        source = Path(package["manifest_path"]).parent
        if not source.is_dir():
            raise RuntimeError(f"Missing resolved notice source for {package['name']}")
        candidates = {p for p in source.iterdir()
                      if p.is_file() and p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))}
        for root in source_roots:
            if source.resolve() == root.resolve() or root.resolve() in source.resolve().parents:
                candidates.update(p for p in root.iterdir() if p.is_file() and
                                  p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")))
        if (package.get("source") or "").startswith("git+"):
            root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                                cwd=source, text=True).strip())
            candidates.update(p for p in root.iterdir() if p.is_file() and
                              p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")))
        if package.get("license_file"):
            candidates.add(source / package["license_file"])
        copied = {}
        identity = package.get("id", package["name"] + "@" + package["version"])
        directory = package["name"] + "-" + package["version"] + "-" + hashlib.sha256(identity.encode()).hexdigest()[:12]
        for original in sorted(candidates):
            if not original.is_file():
                raise RuntimeError(f"Missing declared license file for {package['name']}")
            name = original.name if original.parent.resolve() == source.resolve() else "repository-" + original.name
            target = notices / directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            copied[str(target.relative_to(notices))] = hashlib.sha256(target.read_bytes()).hexdigest()
        records.append({"name": package["name"], "version": package["version"],
                        "cargo_id": identity, "source": package.get("source"),
                        "license": package.get("license"), "files": copied,
                        "missing_upstream_text": not copied})
    notices.mkdir(exist_ok=True)
    (notices / "manifest.json").write_text(json.dumps({
        "inventory_scope": "resolved Cargo metadata source set, including build dependencies",
        "packages": records,
    }, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-source", type=Path, required=True)
    parser.add_argument("--rust-source", type=Path,
                        default=Path(__file__).resolve().parent.parent / "mml-rs")
    parser.add_argument("--target-dir", type=Path,
                        default=Path(__file__).resolve().parent / "build" / "native")
    arguments = parser.parse_args()
    package = Path(__file__).resolve().parent
    framework = arguments.framework_source.resolve()
    source = arguments.rust_source.resolve()
    target = arguments.target_dir.resolve()
    destination = package / "src" / "mml" / "_native"
    destination.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["CARGO_PROFILE_DEV_DEBUG"] = "0"
    environment["CARGO_PROFILE_DEV_CODEGEN_UNITS"] = "64"
    environment["CARGO_INCREMENTAL"] = "0"
    environment["CARGO_BUILD_JOBS"] = "1"
    if sys.platform == "win32":
        environment["CARGO_PROFILE_DEV_OPT_LEVEL"] = "1"
    filename = ("mml_native.dll" if sys.platform == "win32"
                else "libmml_native.dylib" if sys.platform == "darwin"
                else "libmml_native.so")
    pins = json.loads((package / "ci/native-source.json").read_bytes())["native"]
    if source_identity(source)["commit"] != pins["revision"]:
        raise RuntimeError("Native checkout differs from the public source pin")
    if source_identity(framework)["commit"] != pins["framework"]["revision"]:
        raise RuntimeError("Framework checkout differs from the public source pin")
    lock = source / pins["lockfile"]
    if hashlib.sha256(lock.read_bytes()).hexdigest() != pins["cargo_lock_sha256"]:
        raise RuntimeError("Native workspace Cargo.lock differs from its admitted bytes")
    libraries = {}
    for version in (3, 4):
        subprocess.run([
            "cargo", "build", "--locked", "--manifest-path", str(source / "native" / "Cargo.toml"),
            "--target-dir", str(target), "--no-default-features",
            "--features", f"v{version}",
        ], env=environment, check=True)
        packaged_filename = (f"mml_native_v{version}.dll" if sys.platform == "win32"
                             else f"libmml_native_v{version}.so")
        library = destination / packaged_filename
        shutil.copy2(target / "debug" / filename, library)
        libraries[str(version)] = {
            "file": library.name,
            "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        }
    metadata_bytes = subprocess.check_output([
        "cargo", "metadata", "--locked", "--format-version", "1", "--manifest-path",
        str(source / "native" / "Cargo.toml"), "--no-default-features", "--features", "v4",
    ], env=environment)
    evidence = package / ".ci-evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "native-cargo-metadata.json").write_bytes(metadata_bytes)
    metadata = json.loads(metadata_bytes)
    resolved_sdk = [p for p in metadata["packages"] if p["name"] == "lutaml-rs"]
    if len(resolved_sdk) != 1 or not (resolved_sdk[0].get("source") or "").endswith(
            "#" + pins["framework"]["revision"]):
        raise RuntimeError("Resolved SDK differs from the public framework pin")
    capture_runtime_notices(metadata, destination, (source, framework))
    if hashlib.sha256(lock.read_bytes()).hexdigest() != pins["cargo_lock_sha256"]:
        raise RuntimeError("Native build changed its admitted Cargo.lock")
    for checkout in (source, framework):
        subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=checkout, check=True)
    provenance = {
        "native_source": source_identity(source),
        "framework_identity": source_identity(framework),
        "cargo_lock_sha256": hashlib.sha256((source / "native" / "Cargo.lock").read_bytes()).hexdigest(),
        "cargo_metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "runtime_notices": "runtime-licenses/manifest.json",
        "format": "mml-native-python/1",
        "model_manifest": json.loads((source / "model" / "manifest.json").read_text()),
        "libraries": libraries,
        "framework_source": str(framework),
        "rust_source": str(source),
    }
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
