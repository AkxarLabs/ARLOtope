"""The lab's settings: config.defaults.yaml with the sparse config.yaml laid over it (labfiles.config / set_config)."""
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

import labfiles

DEFAULTS = """\
lab:
  name: null
  stale_days: 14
compute:
  scheduler:
    kind: local
    stages: [PILOT, FULL]
agents:
  programmatic:
    enabled: false
    max_minutes: 240
    presets: {}
    backends:
      claude: {model: opus, effort: high}
"""


@pytest.fixture
def hub(tmp_path):
    (tmp_path / "lab").mkdir()
    (tmp_path / "lab" / "config.defaults.yaml").write_text(DEFAULTS, encoding="utf-8")
    return tmp_path


def write(hub, text):
    (hub / "lab" / "config.yaml").write_text(text, encoding="utf-8")


def overrides(hub):
    return yaml.safe_load((hub / "lab" / "config.yaml").read_text(encoding="utf-8")) or {}


def test_no_overrides_file_means_the_defaults(hub):
    assert labfiles.config(hub) == yaml.safe_load(DEFAULTS) and labfiles.config_problems(hub) == []
    assert not (hub / "lab" / "config.yaml").exists()


def test_overrides_merge_dicts_and_replace_lists_and_values(hub):
    write(hub, "lab: {name: Mine}\ncompute: {scheduler: {stages: [FULL]}}\n"
                   "agents: {programmatic: {backends: {claude: {model: sonnet}}}}\n")
    cfg = labfiles.config(hub)
    assert cfg["lab"] == {"name": "Mine", "stale_days": 14}                      # a sibling default survives
    assert cfg["compute"]["scheduler"] == {"kind": "local", "stages": ["FULL"]}  # a list replaces
    assert cfg["agents"]["programmatic"]["backends"]["claude"] == {"model": "sonnet", "effort": "high"}


def test_null_puts_a_setting_back_to_its_default(hub):
    write(hub, "agents: {programmatic: {max_minutes: null, enabled: true}}\n")
    prog = labfiles.config(hub)["agents"]["programmatic"]
    assert prog["max_minutes"] == 240 and prog["enabled"] is True


def test_set_config_keeps_only_what_differs_and_none_resets(hub):
    assert labfiles.set_config(hub, {"agents.programmatic.enabled": True, "lab.stale_days": 30,
                                      "compute.scheduler.stages": ["FULL"]}) is None
    assert overrides(hub) == {"agents": {"programmatic": {"enabled": True}}, "lab": {"stale_days": 30},
                              "compute": {"scheduler": {"stages": ["FULL"]}}}
    assert labfiles.config(hub)["agents"]["programmatic"]["enabled"] is True
    assert labfiles.set_config(hub, {"agents.programmatic.enabled": False, "lab.stale_days": None}) is None   # the default again, and a reset
    assert overrides(hub) == {"compute": {"scheduler": {"stages": ["FULL"]}}}                              # empty sections go too
    assert labfiles.config(hub)["lab"]["stale_days"] == 14


def test_set_config_on_a_block_stores_only_its_differences(hub):
    block = {"kind": "slurm", "stages": ["PILOT", "FULL"]}
    assert labfiles.set_config(hub, {"compute.scheduler": block}) is None
    assert overrides(hub)["compute"]["scheduler"] == {"kind": "slurm"}
    assert labfiles.set_config(hub, {"compute.scheduler": {"kind": "local", "stages": ["PILOT", "FULL"]}}) is None
    assert overrides(hub) == {}


def test_an_open_map_is_replaced_whole(hub):
    assert labfiles.set_config(hub, {"agents.programmatic.presets": {"a": {"backend": "codex"}, "b": {}}}) is None
    assert labfiles.set_config(hub, {"agents.programmatic.presets": {"b": {}}}) is None
    assert labfiles.config(hub)["agents"]["programmatic"]["presets"] == {"b": {}}
    assert labfiles.config_problems(hub) == []


def test_a_file_that_stops_parsing_keeps_the_last_good_settings(hub):
    write(hub, "lab: {name: Mine}\n")
    assert labfiles.config(hub)["lab"]["name"] == "Mine"
    write(hub, "lab: {name: Mine\n  broken: [\n")
    cfg = labfiles.config(hub)
    assert cfg["lab"]["name"] == "Mine" and cfg["compute"]                       # last good, and never {}
    assert "config.yaml is unreadable" in labfiles.config_problems(hub)[0]
    write(hub, "lab: {name: Fixed}\n")
    assert labfiles.config(hub)["lab"]["name"] == "Fixed" and labfiles.config_problems(hub) == []


def test_a_file_that_never_parsed_means_the_defaults_alone(hub):
    write(hub, "- not\n- a mapping\n")
    assert labfiles.config(hub) == yaml.safe_load(DEFAULTS)
    assert "unreadable" in labfiles.config_problems(hub)[0]


def test_set_config_will_not_overwrite_an_unreadable_file(hub):
    write(hub, "lab: [\n")
    assert "unreadable" in labfiles.set_config(hub, {"lab.stale_days": 30})
    assert (hub / "lab" / "config.yaml").read_text(encoding="utf-8") == "lab: [\n"


def test_unknown_keys_and_wrong_types_are_reported(hub):
    write(hub, "lab: {stale_dayz: 3}\nagents: {programmatic: {enabled: 'yes please', max_minutes: 60}}\n"
                   "typo: 1\ncompute: {scheduler: {kind: null}}\n")
    problems = labfiles.config_problems(hub)
    assert sorted(problems) == ["agents.programmatic.enabled should be a bool, not a str",
                                "unknown setting lab.stale_dayz", "unknown setting typo"]


def test_set_config_refuses_unknown_settings_and_wrong_types_and_writes_nothing(hub):
    for changes, why in (({"lab.stale_dayz": 3}, "unknown setting lab.stale_dayz"),
                         ({"lab.stale_days": "soon"}, "lab.stale_days should be a number, not a str"),
                         ({"agents.programmatic.enabled": 1}, "agents.programmatic.enabled should be a bool, not a number"),
                         ({"compute.scheduler.stages": "FULL"}, "compute.scheduler.stages should be a list, not a str")):
        assert why in labfiles.set_config(hub, {**changes, "lab.name": "Ok"})
    assert not (hub / "lab" / "config.yaml").exists()
    assert labfiles.set_config(hub, {"lab.name": "Any text", "lab.stale_days": 3.5}) is None     # null defaults take anything


def test_concurrent_writers_lose_nothing(hub):
    def save(i):
        return labfiles.set_config(hub, {f"agents.programmatic.presets.p{i}": {"n": i}})
    with ThreadPoolExecutor(8) as pool:
        assert set(pool.map(save, range(16))) == {None}
    assert set(overrides(hub)["agents"]["programmatic"]["presets"]) == {f"p{i}" for i in range(16)}
    assert not list((hub / "lab").glob("*.tmp"))


def test_a_fresh_lab_gets_a_header_only_overrides_file(hub):
    path = labfiles.ensure_lab_files(hub)
    assert path.read_text(encoding="utf-8") == labfiles.CONFIG_HEADER and overrides(hub) == {}
    path.write_text("lab: {name: Mine}\n", encoding="utf-8")
    labfiles.ensure_lab_files(hub)
    assert overrides(hub) == {"lab": {"name": "Mine"}}
