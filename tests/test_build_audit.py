"""Tests for apply_ant_fixes and validate_ant_fixes in build_audit.py."""

import pathlib
import sys
import xml.etree.ElementTree as ET
import pytest

sys.path.insert(
    0,
    str(
        pathlib.Path(__file__).parent.parent
        / ".claude"
        / "skills"
        / "jade-core-build-fixer"
        / "scripts"
    ),
)
from build_audit import apply_ant_fixes, analyse_ant

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _analyse(build_path: pathlib.Path):
    return analyse_ant(build_path, "1.7")


def _get_attr_value(xml_text: str, element_tag: str, attr_name: str) -> str | None:
    root = ET.fromstring(xml_text)
    for el in root.iter(element_tag):
        val = el.get(attr_name)
        if val is not None:
            return val
    return None


class TestApplyAntFixesJavacOnly:
    """Fix applies only to <javac> elements, not <javacc> or <antcall>."""

    def test_javac_source_target_updated(self, tmp_path):
        """<javac source="1.5" target="1.5"> -> source="1.7" target="1.7"."""
        src = FIXTURES / "build_javac_only.xml"
        build = tmp_path / "build.xml"
        build.write_text(src.read_text(encoding="utf-8"))
        analysis = _analyse(build)
        fixes = apply_ant_fixes(build, analysis, "1.7")
        xml_text = build.read_text(encoding="utf-8")

        assert _get_attr_value(xml_text, "javac", "source") == "1.7"
        assert _get_attr_value(xml_text, "javac", "target") == "1.7"
        assert len(fixes) == 2
        assert fixes[0]["type"] == "compiler_source"
        assert fixes[1]["type"] == "compiler_target"

    def test_javacc_target_preserved(self, tmp_path):
        """<javacc target="grammar.jj"> must NOT be changed to 1.7."""
        src = FIXTURES / "build_mixed_javac_javacc.xml"
        build = tmp_path / "build.xml"
        build.write_text(src.read_text(encoding="utf-8"))
        analysis = _analyse(build)
        apply_ant_fixes(build, analysis, "1.7")
        xml_text = build.read_text(encoding="utf-8")

        javac_target = _get_attr_value(xml_text, "javac", "target")
        javacc_target = _get_attr_value(xml_text, "javacc", "target")

        assert javac_target == "1.7", "javac target should be updated"
        assert javacc_target == "src/jade/lang/acl/ACLParser.jj", (
            "javacc target (grammar file path) must NOT be changed"
        )

    def test_antcall_target_preserved(self, tmp_path):
        """<antcall target="deploy"> must NOT be changed to 1.7."""
        src = FIXTURES / "build_with_antcall.xml"
        build = tmp_path / "build.xml"
        build.write_text(src.read_text(encoding="utf-8"))
        analysis = _analyse(build)
        apply_ant_fixes(build, analysis, "1.7")
        xml_text = build.read_text(encoding="utf-8")

        antcall_target = _get_attr_value(xml_text, "antcall", "target")
        assert antcall_target == "deploy", "antcall target must NOT be changed"


class TestApplyAntFixesNoJavac:
    """When no <javac> elements exist, only javacc jdkversion is updated."""

    def test_no_javac_no_op(self, tmp_path):
        """XML with only <javacc>: jdkversion updated, target preserved."""
        src = FIXTURES / "build_no_javac.xml"
        build = tmp_path / "build.xml"
        build.write_text(src.read_text(encoding="utf-8"))
        analysis = _analyse(build)
        fixes = apply_ant_fixes(build, analysis, "1.7")
        xml_text = build.read_text(encoding="utf-8")

        assert _get_attr_value(xml_text, "javacc", "jdkversion") == "1.7"
        assert _get_attr_value(xml_text, "javacc", "target") == "grammar.jj"
        assert len(fixes) == 1
        assert fixes[0]["type"] == "javacc_jdkversion"

    def test_no_javac_javacc_target_preserved(self, tmp_path):
        """Only <javacc> present: target="grammar.jj" preserved."""
        src = FIXTURES / "build_no_javac.xml"
        build = tmp_path / "build.xml"
        build.write_text(src.read_text(encoding="utf-8"))
        analysis = _analyse(build)
        apply_ant_fixes(build, analysis, "1.7")
        xml_text = build.read_text(encoding="utf-8")

        assert _get_attr_value(xml_text, "javacc", "target") == "grammar.jj"


class TestRegressionJadeBuildXml:
    """Integration: run against real JADE build.xml with target 1.7."""

    def test_jade_build_xml(self, tmp_path):
        """All javacc target attributes survive, javac get updated."""
        jade_build = pathlib.Path("JADE-4.6.0/src/jade/build.xml")
        if not jade_build.exists():
            pytest.skip("JADE-4.6.0 not available")

        build = tmp_path / "build.xml"
        build.write_text(jade_build.read_text(encoding="utf-8"))
        analysis = _analyse(build)
        apply_ant_fixes(build, analysis, "1.7")
        xml_text = build.read_text(encoding="utf-8")

        root = ET.fromstring(xml_text)
        javac_els = list(root.iter("javac"))
        javacc_els = list(root.iter("javacc"))

        for el in javac_els:
            src = el.get("source")
            tgt = el.get("target")
            if src is not None:
                assert src == "1.7", f"javac source should be 1.7, got {src}"
            if tgt is not None:
                assert tgt == "1.7", f"javac target should be 1.7, got {tgt}"

        for el in javacc_els:
            tgt = el.get("target")
            if tgt is not None:
                assert tgt != "1.7", f"javacc target must not be corrupted: {tgt}"
                assert not (tgt and tgt.replace(".", "").isdigit()), (
                    f"javacc target looks like a version number: {tgt}"
                )
