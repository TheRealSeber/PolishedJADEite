#!/usr/bin/env bash
# Benchmark: compare unchecked-warning count between original and migrated JADE.
# Usage: ./benchmarks/run-benchmark.sh [migrated-dir]
# Example: ./benchmarks/run-benchmark.sh JADE-4.6.0-java1.6

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ORIGINAL_DIR="$ROOT_DIR/JADE-4.6.0"
MIGRATED_DIR="${1:-$ROOT_DIR/JADE-4.6.0-java1.6}"

echo "=== JADE Migration Benchmark ==="
echo "Original : $ORIGINAL_DIR"
echo "Migrated : $MIGRATED_DIR"
echo ""

# ---- helpers ----

count_unchecked() {
  local dir="$1"
  local build_dir="$dir/src/jade"
  if [ ! -f "$build_dir/build.xml" ]; then
    echo "no-build-xml"
    return
  fi
  (cd "$build_dir" && JAVA_HOME=/usr/lib/jvm/java-8-openjdk ant jade 2>&1 | grep -c "\[unchecked\]") || echo 0
}

count_raw_decls() {
  local dir="$1"
  grep -rn "^\s*\(Vector\|Hashtable\|ArrayList\|HashMap\|LinkedList\|HashSet\|List\|Map\|Set\|Collection\) [a-zA-Z]" \
    "$dir" --include="*.java" 2>/dev/null | grep -v "<\|import\|//\|\*" | wc -l || echo 0
}

count_raw_inst() {
  local dir="$1"
  grep -rl "new Vector()\|new Hashtable()\|new ArrayList()\|new HashMap()\|new LinkedList()\|new HashSet()" \
    "$dir" --include="*.java" 2>/dev/null | wc -l || echo 0
}

count_for_loops() {
  local dir="$1"
  grep -rn "for.*int [a-z].*=.*0.*\.size()\|for.*int [a-z].*=.*0.*\.length" \
    "$dir" --include="*.java" 2>/dev/null | grep -v "//\|\*" | wc -l || echo 0
}

# ---- scan original ----

echo "--- Original ($ORIGINAL_DIR) ---"
ORIG_RAW_INST=$(count_raw_inst "$ORIGINAL_DIR")
ORIG_RAW_DECL=$(count_raw_decls "$ORIGINAL_DIR")
ORIG_FOR=$(count_for_loops "$ORIGINAL_DIR")
echo "Raw instantiations (files) : $ORIG_RAW_INST"
echo "Raw declarations (lines)   : $ORIG_RAW_DECL"
echo "For-loop candidates        : $ORIG_FOR"

if command -v ant &>/dev/null && [ -f "$ORIGINAL_DIR/src/jade/build.xml" ] && [ -d "/usr/lib/jvm/java-8-openjdk" ]; then
  echo "Compiling original..."
  ORIG_UNCHECKED=$(count_unchecked "$ORIGINAL_DIR")
  echo "Unchecked warnings         : $ORIG_UNCHECKED"
else
  ORIG_UNCHECKED="N/A"
  echo "Unchecked warnings         : N/A (ant not available or no build.xml)"
fi

echo ""

# ---- scan migrated ----

if [ ! -d "$MIGRATED_DIR" ]; then
  echo "Migrated directory not found: $MIGRATED_DIR"
  echo "Run the migration skills first, then re-run this benchmark."
  exit 1
fi

echo "--- Migrated ($MIGRATED_DIR) ---"
MIG_RAW_INST=$(count_raw_inst "$MIGRATED_DIR")
MIG_RAW_DECL=$(count_raw_decls "$MIGRATED_DIR")
MIG_FOR=$(count_for_loops "$MIGRATED_DIR")
echo "Raw instantiations (files) : $MIG_RAW_INST"
echo "Raw declarations (lines)   : $MIG_RAW_DECL"
echo "For-loop candidates        : $MIG_FOR"

if command -v ant &>/dev/null && [ -f "$MIGRATED_DIR/src/jade/build.xml" ] && [ -d "/usr/lib/jvm/java-8-openjdk" ]; then
  echo "Compiling migrated..."
  MIG_UNCHECKED=$(count_unchecked "$MIGRATED_DIR")
  echo "Unchecked warnings         : $MIG_UNCHECKED"
else
  MIG_UNCHECKED="N/A"
  echo "Unchecked warnings         : N/A (ant not available or no build.xml)"
fi

echo ""

# ---- delta report ----

echo "--- Delta ---"
if [[ "$ORIG_RAW_INST" =~ ^[0-9]+$ && "$MIG_RAW_INST" =~ ^[0-9]+$ ]]; then
  echo "Raw inst files removed : $((ORIG_RAW_INST - MIG_RAW_INST)) / $ORIG_RAW_INST"
fi
if [[ "$ORIG_RAW_DECL" =~ ^[0-9]+$ && "$MIG_RAW_DECL" =~ ^[0-9]+$ ]]; then
  echo "Raw decl lines fixed   : $((ORIG_RAW_DECL - MIG_RAW_DECL)) / $ORIG_RAW_DECL"
fi
if [[ "$ORIG_FOR" =~ ^[0-9]+$ && "$MIG_FOR" =~ ^[0-9]+$ ]]; then
  echo "For-loops converted    : $((ORIG_FOR - MIG_FOR)) / $ORIG_FOR"
fi
if [[ "$ORIG_UNCHECKED" =~ ^[0-9]+$ && "$MIG_UNCHECKED" =~ ^[0-9]+$ ]]; then
  echo "Unchecked warnings cut : $((ORIG_UNCHECKED - MIG_UNCHECKED)) / $ORIG_UNCHECKED"
fi

echo ""
echo "=== Done ==="
