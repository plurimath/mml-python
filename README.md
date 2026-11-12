# Native MathML for Python

This local source candidate uses generated Rust MathML v3 and v4 models,
presence-aware typed snapshots, and native XML codecs.

    from mml import parse
    with parse('<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>') as model:
        attributes = model.snapshot()
        xml = model.to_xml()

Select version=4 for MathML v4 and model="Mi" for a standalone identifier.
NativeError.details retains the generated codec error fields.
The model owns its native handle until close() or context exit.

The candidate wheel contains version-specific native libraries. Its provenance
records the exact generated declarations and framework source.
Build native libraries before creating a wheel. The sibling mml-rs/native
crate and its version features contain the corresponding ABI source.

To build from the paired local source candidates, prepare the pinned framework
source with the snapshot generator patch and run the following commands.

    python build_native.py --framework-source /path/to/lutaml-rs
    python -m pip wheel --no-build-isolation --no-deps .

The native build uses one target directory for both version-specific libraries.

The snapshot profile is mml-typed-model-snapshot-v1. It retains native present
empty values and nulls, omits absent fields, and includes __lml_content ordering
tokens. Numeric scalar fields use portable-exact-json-v1 strings. Ruby getter
defaults and ordinary JSON behavior have independent source-oracle receipts.

## Source compatibility observations

Ruby stores the integer input 9007199254740993 as 9007199254740992 in the probed
Mglyph field. The native candidate retains the exact input value.
An empty Ruby Mi getter returns a value collection containing an empty string.
The native candidate records absent text content as absent.
Ruby null/default getters and native field presence are recorded separately.
These cases remain explicit compatibility differences in the qualification
receipt.

Public-source builds use the pinned native workspace lock and SDK Git revision.
The wheel retains original model-source notices under `licenses`;
`runtime-licenses/manifest.json` records actual resolved build-source notices,
including explicit missing-upstream-text entries.
