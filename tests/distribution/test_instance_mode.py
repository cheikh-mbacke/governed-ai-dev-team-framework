"""Instance-only install policy (standalone removed)."""

from __future__ import annotations

import json
from pathlib import Path

from distribution.installer.instance_mode import (
    fresh_install_product_code_error,
    is_standalone_in_tree_install,
    list_application_markers,
    update_standalone_refused_error,
)
from distribution.installer.record import INSTALLATION_RECORD_FILE


def test_list_application_markers_detects_src_and_root_py(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("y\n", encoding="utf-8")
    markers = list_application_markers(tmp_path)
    assert "src/" in markers
    assert "main.py" in markers


def test_fresh_install_product_code_error(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    err = fresh_install_product_code_error(tmp_path)
    assert err is not None
    assert "Fresh install refused" in err
    assert "migrate_to_instance" in err


def test_empty_instance_has_no_product_error(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    assert fresh_install_product_code_error(tmp_path) is None


def test_standalone_detection_requires_install_and_markers(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    assert is_standalone_in_tree_install(tmp_path) is False
    record = tmp_path / INSTALLATION_RECORD_FILE
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"schema_version": 3, "project_id": "x"}), encoding="utf-8")
    assert is_standalone_in_tree_install(tmp_path) is False
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert is_standalone_in_tree_install(tmp_path) is True
    err = update_standalone_refused_error(tmp_path)
    assert err is not None
    assert "Update refused" in err
