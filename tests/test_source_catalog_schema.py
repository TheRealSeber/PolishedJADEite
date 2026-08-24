import json
import pathlib

from jsonschema import validate


CATALOG_PATH = pathlib.Path("docs/sources/migration-source-catalog.json")
SCHEMA_PATH = pathlib.Path("docs/sources/schema/migration-source-catalog.schema.json")


def test_source_catalog_and_path_files_validate_against_schema():
    assert CATALOG_PATH.exists(), f"Missing catalog: {CATALOG_PATH}"
    assert SCHEMA_PATH.exists(), f"Missing schema: {SCHEMA_PATH}"

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    validate(instance=catalog, schema=schema)

    assert catalog["document_type"] == "migration_source_catalog"
    assert len(catalog["paths"]) == 8

    for entry in catalog["paths"]:
        rel_path = pathlib.Path(entry["file"])
        path_file = CATALOG_PATH.parent / rel_path
        assert path_file.exists(), f"Missing split file: {path_file}"
        path_payload = json.loads(path_file.read_text(encoding="utf-8"))
        validate(instance=path_payload, schema=schema)
        assert path_payload["document_type"] == "migration_source_path"
        assert path_payload["path_id"] == entry["path_id"]
