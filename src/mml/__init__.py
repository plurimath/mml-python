"""MathML models owned by the generated native codec runtime."""

import ctypes
import json
from pathlib import Path
import threading
import weakref

__all__ = ["parse", "NativeModel", "NativeError", "runtime_info"]
_runtimes = {}
_runtime_lock = threading.RLock()


class NativeError(ValueError):
    """A structured failure returned by the native model or XML codec."""

    def __init__(self, details):
        self.details = details
        self.reason = details.get("reason", details.get("category"))
        super().__init__(details.get("detail") or str(self.reason))


class _Runtime:
    def __init__(self, version):
        path = Path(__file__).parent / "_native" / f"libmml_native_v{version}.so"
        self.library = ctypes.CDLL(str(path))
        for name in ("mml_native_info", "mml_native_parse",
                     "mml_native_snapshot", "mml_native_xml"):
            getattr(self.library, name).restype = ctypes.c_void_p
        self.library.mml_native_info.argtypes = []
        self.library.mml_native_parse.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
        self.library.mml_native_snapshot.argtypes = [ctypes.c_void_p]
        self.library.mml_native_xml.argtypes = [ctypes.c_void_p]
        self.library.mml_native_free.argtypes = [ctypes.c_void_p]
        self.library.mml_native_free.restype = None
        self.library.mml_native_string_free.argtypes = [ctypes.c_void_p]
        self.library.mml_native_string_free.restype = None

    def result(self, pointer):
        if not pointer:
            raise RuntimeError("Native runtime returned a null response")
        try:
            response = json.loads(ctypes.string_at(pointer))
        finally:
            self.library.mml_native_string_free(pointer)
        if not response["ok"]:
            raise NativeError(response["error"])
        return response["value"]


def _runtime(version):
    if type(version) is not int or version not in (3, 4):
        raise ValueError("MathML version must be 3 or 4")
    with _runtime_lock:
        if version not in _runtimes:
            _runtimes[version] = _Runtime(version)
        return _runtimes[version]


def runtime_info(version=3):
    """Return the native runtime's source-model manifest and JSON profile."""
    runtime = _runtime(version)
    return runtime.result(runtime.library.mml_native_info())


class NativeModel:
    """An owned typed model whose snapshot and XML use the same native handle."""

    def __init__(self, runtime, handle, version, model):
        self._runtime = runtime
        self._lock = threading.RLock()
        self._finalizer = weakref.finalize(
            self, runtime.library.mml_native_free, handle)
        self._handle = handle
        self.version = version
        self.model = model

    def _project(self, function):
        with self._lock:
            if self._handle is None:
                raise ValueError("Native model is closed")
            return self._runtime.result(function(self._handle))

    def snapshot(self):
        """Return presence-aware native fields and XML ordering metadata."""
        return self._project(self._runtime.library.mml_native_snapshot)

    def to_xml(self):
        """Serialize XML from the same parsed typed model."""
        return self._project(self._runtime.library.mml_native_xml)

    def close(self):
        with self._lock:
            if self._handle is not None:
                self._handle = None
                self._finalizer()

    def __enter__(self):
        with self._lock:
            if self._handle is None:
                raise ValueError("Native model is closed")
        return self

    def __exit__(self, *_):
        self.close()


def parse(xml, *, version=3, model="Math"):
    """Parse a Math or Mi XML root into an owned generated native model."""
    runtime = _runtime(version)
    if model not in ("Math", "Mi"):
        raise ValueError("Root model must be Math or Mi")
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    if not isinstance(xml, bytes):
        raise TypeError("XML must be str or bytes")
    buffer = ctypes.create_string_buffer(xml)
    result = runtime.result(runtime.library.mml_native_parse(
        buffer, len(xml), 0 if model == "Math" else 1))
    return NativeModel(runtime, result["handle"], version, model)
