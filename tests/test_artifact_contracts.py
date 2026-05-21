import json


def test_run_config_has_required_keys():
    cfg = json.load(open('migration-runs/sample/artifacts/00-run-config.json', encoding='utf-8'))
    assert 'run_id' in cfg and 'workspace_path' in cfg and 'artifacts_path' in cfg
