from pathlib import Path
from setuptools import setup, find_packages
from wheel.bdist_wheel import bdist_wheel

class NativeWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, _, platform = super().get_tag()
        return "py3", "none", platform

root = Path(__file__).parent
for version in (3, 4):
    library = root / "src" / "mml" / "_native" / f"libmml_native_v{version}.so"
    if not library.is_file():
        raise RuntimeError(f"Build the MathML v{version} native library before packaging")

setup(
    name="mml", version="0.1.0",
    description="Native generated MathML models and XML codecs",
    packages=find_packages("src"), package_dir={"": "src"},
    package_data={"mml": ["_native/*.so", "_native/provenance.json"]},
    python_requires=">=3.10", cmdclass={"bdist_wheel": NativeWheel},
)
