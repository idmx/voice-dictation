"""Validate the PyInstaller spec file."""

from __future__ import annotations

import ast
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parents[2] / "voice_dictation.spec"


class TestSpecFile:
    def test_spec_file_exists(self) -> None:
        assert SPEC_PATH.exists(), f"Spec file not found at {SPEC_PATH}"
        assert SPEC_PATH.is_file()

    def test_spec_parses(self) -> None:
        """Spec file must be valid Python and parse as AST."""
        content = SPEC_PATH.read_text(encoding="utf-8")
        ast.parse(content)

    def test_spec_executes_in_sandbox(self) -> None:
        """Spec file must execute without raising in a sandbox."""
        content = SPEC_PATH.read_text(encoding="utf-8")
        sandbox: dict = {}

        # Provide stubs for PyInstaller spec globals.
        # Analysis must return an object with a mutable `hiddenimports` list
        # because the spec appends platform-specific imports to it.
        analysis_stub = _AnalysisStub()
        sandbox["Analysis"] = analysis_stub
        sandbox["PYZ"] = _stub_collector("PYZ")
        sandbox["EXE"] = _stub_collector("EXE")
        sandbox["COLLECT"] = _stub_collector("COLLECT")
        sandbox["BUNDLE"] = _stub_collector("BUNDLE")
        sandbox["__name__"] = "voice_dictation_spec_test"

        exec(compile(content, str(SPEC_PATH), "exec"), sandbox)

        # The Analysis stub should have been called
        assert len(analysis_stub.calls) >= 1, "Analysis() was not called"

    def test_spec_contains_entry_point(self) -> None:
        """Spec must reference __main__.py."""
        content = SPEC_PATH.read_text(encoding="utf-8")
        assert "__main__.py" in content, "Entry point __main__.py not found in spec"

    def test_spec_contains_icons(self) -> None:
        """Spec must include assets/icons in datas."""
        content = SPEC_PATH.read_text(encoding="utf-8")
        assert "assets/icons" in content, "assets/icons not found in spec datas"

    def test_spec_excludes_tests(self) -> None:
        """Spec must exclude test modules."""
        content = SPEC_PATH.read_text(encoding="utf-8")
        assert "pytest" in content, "pytest not in excludes"
        assert "tests" in content, "tests not in excludes"

    def test_spec_hidden_imports(self) -> None:
        """Spec must declare key hidden imports."""
        content = SPEC_PATH.read_text(encoding="utf-8")
        required = ["sounddevice", "numpy", "pynput", "pystray", "loguru", "pydantic"]
        for imp in required:
            assert imp in content, f"Hidden import '{imp}' missing from spec"

    def test_spec_app_bundle_identifier(self) -> None:
        """Spec must set a bundle identifier for the macOS app."""
        content = SPEC_PATH.read_text(encoding="utf-8")
        assert "bundle_identifier" in content
        assert "com.alfagen.voice-dictation" in content


class _AnalysisStub:
    """Stub for PyInstaller's Analysis that returns an object with hiddenimports."""

    def __init__(self) -> None:
        self.calls: list = []

    def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        result = _AnalysisResult(kwargs.get("hiddenimports", []))
        result.pure = object()
        result.zipped_data = []
        result.scripts = []
        result.binaries = []
        result.zipfiles = []
        result.datas = kwargs.get("datas", [])
        return result


class _AnalysisResult:
    """Mimics the object returned by Analysis()."""

    def __init__(self, hiddenimports: list) -> None:
        self.hiddenimports = list(hiddenimports)
        self.pure: object = object()
        self.zipped_data: list = []
        self.scripts: list = []
        self.binaries: list = []
        self.zipfiles: list = []
        self.datas: list = []


class _StubCollector:
    """Helper to record calls to PyInstaller spec functions."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list = []

    def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return {"name": self.name, "calls": self.calls}

    def __getattr__(self, item: str) -> object:
        return self


def _stub_collector(name: str) -> _StubCollector:
    return _StubCollector(name)
