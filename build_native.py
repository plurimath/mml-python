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


def capture_runtime_notices(metadata, destination):
    """Retain actual resolved-source notices separately from the model-source notices."""
    notices = destination / "runtime-licenses"
    records = []
    for package in metadata["packages"]:
        source = Path(package["manifest_path"]).parent
        if not source.is_dir():
            raise RuntimeError(f"Missing resolved notice source for {package['name']}")
        candidates = {p for p in source.iterdir()
                      if p.is_file() and p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))}
        if package.get("license_file"):
            candidates.add(source / package["license_file"])
        copied = {}
        for original in sorted(candidates):
            if not original.is_file():
                raise RuntimeError(f"Missing declared license file for {package['name']}")
            target = notices / (package["name"] + "-" + package["version"]) / original.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            copied[str(target.relative_to(notices))] = hashlib.sha256(target.read_bytes()).hexdigest()
        records.append({"name": package["name"], "version": package["version"],
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
    if sys.platform == "win32":
        environment["CARGO_PROFILE_DEV_OPT_LEVEL"] = "1"
    filename = ("mml_native.dll" if sys.platform == "win32"
                else "libmml_native.dylib" if sys.platform == "darwin"
                else "libmml_native.so")
    libraries = {}
    for version in (3, 4):
        subprocess.run([
            "cargo", "--config",
            f"patch.crates-io.lutaml-rs.path={json.dumps(str(framework))}",
            "build", "--locked", "--manifest-path", str(source / "native" / "Cargo.toml"),
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
        "cargo", "--config", f"patch.crates-io.lutaml-rs.path={json.dumps(str(framework))}",
        "metadata", "--locked", "--format-version", "1", "--manifest-path",
        str(source / "native" / "Cargo.toml"), "--no-default-features", "--features", "v4",
    ], env=environment)
    capture_runtime_notices(json.loads(metadata_bytes), destination)
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
