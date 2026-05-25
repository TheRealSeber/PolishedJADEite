# Build Fixer — Scoped `<javac>` Attribute Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `apply_ant_fixes()` global regex that corrupts non-`<javac>` `target`/`source` attributes, and add post-fix XML validation.

**Architecture:** Scope the `source=` and `target=` regex patterns to anchor on `<javac\b` prefix (3 lines changed). Add a `validate_ant_fixes()` function that parses XML before/after and warns about collisions (25 lines new). Hook into main flow after fix application (3 lines new).

**Tech Stack:** Python, `re`, `xml.etree.ElementTree`, pytest

**Spec:** `docs/superpowers/specs/2026-05-25-build-fixer-javac-scope-fix-design.md`

---

## File Map

| File | Role |
|------|------|
| `.claude/skills/jade-core-build-fixer/scripts/build_audit.py` | Two functions modified, one added |
| `tests/test_build_audit.py` | New: 4 test fixtures + 5 test cases |

---

### Task 1: Create test fixtures (XML files)

**Files:**
- Create: `tests/fixtures/build_javac_only.xml`
- Create: `tests/fixtures/build_mixed_javac_javacc.xml`
- Create: `tests/fixtures/build_with_antcall.xml`
- Create: `tests/fixtures/build_no_javac.xml`

- [ ] **Step 1: Write `build_javac_only.xml`**

```xml
<project name="test" basedir=".">
    <target name="compile">
        <javac srcdir="src" destdir="build" source="1.5" target="1.5"/>
    </target>
</project>
```

Save to: `tests/fixtures/build_javac_only.xml`

- [ ] **Step 2: Write `build_mixed_javac_javacc.xml`**

```xml
<project name="test" basedir=".">
    <target name="parser" depends="init" if="makeParsers">
        <javacc jdkversion="1.4" javacchome="${env.JAVACC_HOME}" outputdirectory="src/jade/lang/acl" target="src/jade/lang/acl/ACLParser.jj"/>
    </target>
    <target name="compile">
        <javac srcdir="src" destdir="build" source="1.5" target="1.5"/>
    </target>
</project>
```

Save to: `tests/fixtures/build_mixed_javac_javacc.xml`

- [ ] **Step 3: Write `build_with_antcall.xml`**

```xml
<project name="test" basedir=".">
    <target name="main" depends="compile">
        <antcall target="deploy"/>
    </target>
    <target name="compile">
        <javac srcdir="src" destdir="build" source="1.5" target="1.5"/>
    </target>
    <target name="deploy">
        <echo message="deployed"/>
    </target>
</project>
```

Save to: `tests/fixtures/build_with_antcall.xml`

- [ ] **Step 4: Write `build_no_javac.xml`**

```xml
<project name="test" basedir=".">
    <target name="parse" if="make">
        <javacc jdkversion="1.4" target="grammar.jj"/>
    </target>
</project>
```

Save to: `tests/fixtures/build_no_javac.xml`

- [ ] **Step 5: Create fixtures directory and commit**

Run: `mkdir tests\fixtures 2>nul & echo done`
Then commit fixtures.

---

### Task 2: Write unit tests

**Files:**
- Create: `tests/test_build_audit.py`

- [ ] **Step 1: Write test file**

```python
"""Tests for apply_ant_fixes and validate_ant_fixes in build_audit.py."""
import pathlib
import sys
import xml.etree.ElementTree as ET
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / ".claude" / "skills" / "jade-core-build-fixer" / "scripts"))
from build_audit import apply_ant_fixes, analyse_ant, version_key

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _analyse(build_path: pathlib.Path):
    raw = build_path.read_text(encoding="utf-8")
    return analyse_ant(raw, build_path)


def _get_attr_value(xml_text: str, element_tag: str, attr_name: str) -> str | None:
    root = ET.fromstring(xml_text)
    for el in root.iter(element_tag):
        val = el.get(attr_name)
        if val is not None:
            return val
    return None


def _count_elements(xml_text: str, tag: str) -> int:
    root = ET.fromstring(xml_text)
    return len(list(root.iter(tag)))


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
        assert javacc_target == "src/jade/lang/acl/ACLParser.jj", \
            "javacc target (grammar file path) must NOT be changed"

    def test_antcall_target_preserved(self, tmp_path):
        """<antcall target="deploy"> must NOT be changed to 1.7."""
        src = FIXTURES / "build_with_antcall.xml"
        build = tmp_path / "build.xml"
        build.write_text(src.read_text(encoding="utf-8"))
        analysis = _analyse(build)
        apply_ant_fixes(build, analysis, "1.7")
        xml_text = build.read_text(encoding="utf-8")

        antcall_target = _get_attr_value(xml_text, "antcall", "target")
        assert antcall_target == "deploy", \
            "antcall target must NOT be changed"


class TestApplyAntFixesNoJavac:
    """When no <javac> elements exist, nothing is changed."""

    def test_no_javac_no_op(self, tmp_path):
        """XML with only <javacc> should be unchanged."""
        src = FIXTURES / "build_no_javac.xml"
        build = tmp_path / "build.xml"
        build.write_text(src.read_text(encoding="utf-8"))
        original = build.read_text(encoding="utf-8")
        analysis = _analyse(build)
        fixes = apply_ant_fixes(build, analysis, "1.7")
        result = build.read_text(encoding="utf-8")

        assert result == original, "File with no <javac> must be unchanged"
        assert len(fixes) == 0

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
        jade_build = pathlib.Path(
            "JADE-4.6.0/src/jade/build.xml"
        )
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

        # All javac elements should have target=1.7 and source=1.7
        for el in javac_els:
            src = el.get("source")
            tgt = el.get("target")
            if src is not None:
                assert src == "1.7", f"javac source should be 1.7, got {src}"
            if tgt is not None:
                assert tgt == "1.7", f"javac target should be 1.7, got {tgt}"

        # All javacc target attributes must NOT be version strings
        for el in javacc_els:
            tgt = el.get("target")
            if tgt is not None:
                assert tgt != "1.7", \
                    f"javacc target must not be corrupted: {tgt}"
                assert not (tgt and tgt.replace(".", "").isdigit()), \
                    f"javacc target looks like a version number: {tgt}"
```

Save to: `tests/test_build_audit.py`

- [ ] **Step 2: Run tests and verify they FAIL**

Run: `python -m pytest tests/test_build_audit.py -v`

Expected: `test_javacc_target_preserved` FAILS (javacc target still gets corrupted)
Expected: `test_antcall_target_preserved` FAILS (antcall target still gets corrupted)

---

### Task 3: Fix the regex in `apply_ant_fixes()`

**Files:**
- Modify: `.claude/skills/jade-core-build-fixer/scripts/build_audit.py:511-514`
- Modify: `.claude/skills/jade-core-build-fixer/scripts/build_audit.py:525-528`

- [ ] **Step 1: Fix `source` regex (lines 511-514)**

Change:
```python
raw, count = re.subn(
    r'(\bsource\s*=\s*["\'])([^"\']*?)(["\'])',
    rf"\g<1>{target_version}\g<3>",
    raw,
)
```

To:
```python
raw, count = re.subn(
    r'(<javac\b[^>]*?\bsource\s*=\s*["\'])([^"\']*?)(["\'])',
    rf"\g<1>{target_version}\g<3>",
    raw,
)
```

- [ ] **Step 2: Fix `target` regex (lines 525-528)**

Change:
```python
raw, count = re.subn(
    r'(\btarget\s*=\s*["\'])([^"\']*?)(["\'])',
    rf"\g<1>{target_version}\g<3>",
    raw,
)
```

To:
```python
raw, count = re.subn(
    r'(<javac\b[^>]*?\btarget\s*=\s*["\'])([^"\']*?)(["\'])',
    rf"\g<1>{target_version}\g<3>",
    raw,
)
```

- [ ] **Step 3: Run tests and verify they PASS**

Run: `python -m pytest tests/test_build_audit.py -v`

Expected: All 6 tests PASS

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/jade-core-build-fixer/scripts/build_audit.py tests/test_build_audit.py tests/fixtures/
git commit -m "fix(build-fixer): scope javac source/target regex to <javac> elements only

Prevents corruption of non-javac target attributes (javacc, antcall)."
```

---

### Task 4: Add `validate_ant_fixes()` post-fix validation

**Files:**
- Modify: `.claude/skills/jade-core-build-fixer/scripts/build_audit.py` (add function after line 559)

- [ ] **Step 1: Add `validate_ant_fixes()` function**

Insert after `apply_ant_fixes()` (after line 559), before the Docker helpers:

```python
def validate_ant_fixes(
    original_text: str, fixed_text: str, target_version: str
) -> List[str]:
    """Verify fix correctness: javac attributes updated, no collision damage.

    Returns list of warning strings (empty = clean).
    """
    warnings: List[str] = []
    try:
        orig_root = ET.fromstring(original_text)
        fixed_root = ET.fromstring(fixed_text)
    except ET.ParseError:
        return ["XML parse error — cannot validate fixes"]

    # 1. Verify <javac> source/target are present and match target_version
    for el in fixed_root.iter("javac"):
        for attr in ("source", "target"):
            val = el.get(attr)
            if val is not None and val != target_version:
                warnings.append(
                    f"<javac> {attr}={val} does not match target "
                    f"version {target_version}"
                )

    # 2. Verify <javacc> target was NOT mutated to target_version
    for el in fixed_root.iter("javacc"):
        val = el.get("target")
        if val is not None and val == target_version:
            warnings.append(
                f"<javacc> target corrupted: changed to '{target_version}'"
            )

    # 3. Verify <antcall> target was NOT mutated to target_version
    for el in fixed_root.iter("antcall"):
        val = el.get("target")
        if val is not None and val == target_version:
            warnings.append(
                f"<antcall> target corrupted: changed to '{target_version}'"
            )

    return warnings
```

This goes right after line 559 (end of `apply_ant_fixes`), before the Docker helpers comment block.

- [ ] **Step 2: Write validation tests**

Add to `tests/test_build_audit.py`:

```python
class TestValidateAntFixes:
    """Post-fix validation warns about corrupted attributes."""

    def test_clean_fix_no_warnings(self):
        """Validation returns empty list when fix is correct."""
        from build_audit import validate_ant_fixes

        original = '<project><javac source="1.5" target="1.5"/></project>'
        fixed = '<project><javac source="1.7" target="1.7"/></project>'
        warnings = validate_ant_fixes(original, fixed, "1.7")
        assert warnings == []

    def test_javacc_corruption_detected(self):
        """javacc target changed to version string is flagged."""
        from build_audit import validate_ant_fixes

        original = '<project><javacc target="grammar.jj"/></project>'
        fixed = '<project><javacc target="1.7"/></project>'
        warnings = validate_ant_fixes(original, fixed, "1.7")
        assert len(warnings) == 1
        assert "javacc" in warnings[0].lower()
        assert "corrupted" in warnings[0].lower()

    def test_antcall_corruption_detected(self):
        """antcall target changed to version string is flagged."""
        from build_audit import validate_ant_fixes

        original = '<project><antcall target="deploy"/></project>'
        fixed = '<project><antcall target="1.7"/></project>'
        warnings = validate_ant_fixes(original, fixed, "1.7")
        assert len(warnings) == 1
        assert "antcall" in warnings[0].lower()
```

Add these at the end of the file.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_build_audit.py -v`

Expected: All tests PASS (including new validation tests)

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/jade-core-build-fixer/scripts/build_audit.py tests/test_build_audit.py
git commit -m "feat(build-fixer): add validate_ant_fixes post-fix XML validation"
```

---

### Task 5: Hook validation into main flow

**Files:**
- Modify: `.claude/skills/jade-core-build-fixer/scripts/build_audit.py` (after line 883)

- [ ] **Step 1: Add validation hook after fix application**

Find this block (near line 882):
```python
if build_system == "ant":
    applied_fixes.extend(apply_ant_fixes(build_path, analysis, target_version))
```

Replace with:
```python
if build_system == "ant":
    original_build_text = build_path.read_text(encoding="utf-8", errors="replace")
    applied_fixes.extend(apply_ant_fixes(build_path, analysis, target_version))
    fix_warnings = validate_ant_fixes(
        original_build_text,
        build_path.read_text(encoding="utf-8", errors="replace"),
        target_version,
    )
    if fix_warnings:
        for w in fix_warnings:
            print(f"[WARN] build_audit: {w}", file=sys.stderr)
        audit["fix_validation_warnings"] = fix_warnings
```

(`sys.stderr` and `sys` are already imported at the top of the file.)

- [ ] **Step 2: Verify import works**

Run: `python -c "from build_audit import apply_ant_fixes, validate_ant_fixes; print('both imported')"`
Workdir: `.claude/skills/jade-core-build-fixer/scripts`

- [ ] **Step 3: Integration test — run build_audit against JADE workspace**

Run the full build_audit script against a workspace copy to verify no warnings emitted:
```
python .claude/skills/jade-core-build-fixer/scripts/build_audit.py \
  --build-file migration-runs/jade-1.6-to-1.7/workspace/src/jade/build.xml \
  --target-version 1.7 \
  --artifacts migration-runs/jade-1.6-to-1.7/workspace/artifacts \
  --run-id jade-1.6-to-1.7
```
(Adjust flags to match actual build_audit.py CLI)

Expected: No `[WARN] build_audit:` lines on stderr.

- [ ] **Step 4: Verify JADE build.xml is correct after fix**

Run: `python -c "import xml.etree.ElementTree as ET; root=ET.parse('migration-runs/jade-1.6-to-1.7/workspace/src/jade/build.xml'); [print(el.get('target')) for el in root.iter('javacc')]"`
Expected: Outputs file paths (`src/jade/lang/acl/ACLParser.jj` etc.), NOT `1.7`

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/jade-core-build-fixer/scripts/build_audit.py tests/test_build_audit.py
git commit -m "feat(build-fixer): hook validate_ant_fixes into audit flow"
```

---

### Task 6: Re-run full migration to verify no regression

**Files:**
- Check: `migration-runs/jade-1.6-to-1.7/workspace/src/jade/build.xml`

- [ ] **Step 1: Revert workspace build.xml to baseline and re-run build fixer**

```bash
copy JADE-4.6.0\src\jade\build.xml migration-runs\jade-1.6-to-1.7\workspace\src\jade\build.xml
```

Then run the build_audit.py with the fixed code against 1.7 target.

- [ ] **Step 2: Verify javacc targets survive**

Run the same ElementTree check from Task 5 Step 4.

- [ ] **Step 3: Verify build still passes**

Run: `docker run ... ant jade` (from the workspace).

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "test(build-fixer): verify javacc target preservation on JADE 1.6->1.7"
```
