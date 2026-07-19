import pytest
import yaml

from sirchatalot.config import ConfigError, load_config
from tests.conftest import BASE_CONFIG, make_config


def write_config(tmp_path, data):
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.dump(data), encoding='utf-8')
    return str(path)


def test_example_config_is_valid():
    cfg = load_config('config.yaml.example')
    assert cfg.default_model in [m.name for m in cfg.models]


def test_minimal_config(tmp_path):
    cfg = load_config(write_config(tmp_path, BASE_CONFIG))
    assert cfg.files is None and cfg.audio is None
    assert cfg.agent.max_iterations == 5


def test_missing_file():
    with pytest.raises(ConfigError, match='not found'):
        load_config('/nonexistent/config.yaml')


def test_invalid_yaml(tmp_path):
    path = tmp_path / 'config.yaml'
    path.write_text('telegram: [unclosed', encoding='utf-8')
    with pytest.raises(ConfigError, match='valid YAML'):
        load_config(str(path))


def test_unknown_key_rejected(tmp_path):
    data = {**BASE_CONFIG, 'nonexistent_section': {}}
    with pytest.raises(ConfigError, match='nonexistent_section'):
        load_config(write_config(tmp_path, data))


def test_default_model_must_exist():
    with pytest.raises(Exception, match='default_model'):
        make_config(default_model='ghost')


def test_fallback_chain_must_exist():
    with pytest.raises(Exception, match='fallback_chain'):
        make_config(fallback_chain=['ghost'])


def test_duplicate_model_names():
    models = [dict(BASE_CONFIG['models'][0]), dict(BASE_CONFIG['models'][0])]
    with pytest.raises(Exception, match='duplicate'):
        make_config(models=models, fallback_chain=[])
