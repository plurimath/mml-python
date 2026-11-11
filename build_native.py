"""Build the sibling generated Rust codec crate for this Python package."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


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
    filename = ("mml_native.dll" if sys.platform == "win32"
                else "libmml_native.dylib" if sys.platform == "darwin"
                else "libmml_native.so")
    libraries = {}
    for version in (3, 4):
        subprocess.run([
            "cargo", "--config",
            f"patch.crates-io.lutaml-rs.path={json.dumps(str(framework))}",
            "build", "--manifest-path", str(source / "native" / "Cargo.toml"),
            "--target-dir", str(target), "--no-default-features",
            "--features", f"v{version}",
        ], env=environment, check=True)
        library = destination / f"libmml_native_v{version}.so"
        shutil.copy2(target / "debug" / filename, library)
        libraries[str(version)] = {
            "file": library.name,
            "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        }
    provenance = {
        "format": "mml-native-python/1",
        "model_manifest": json.loads((source / "model" / "manifest.json").read_text()),
        "libraries": libraries,
        "framework_source": str(framework),
        "rust_source": str(source),
    }
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
