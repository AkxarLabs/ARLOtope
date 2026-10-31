"""An installed copy runs from the app folder with the Lab elsewhere: the app folder is never a Lab."""

from conftest import REPO, load


def test_scheduler_ignores_the_app_folder_an_installed_copy_starts_from(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    import ctx
    monkeypatch.setattr(ctx, "_listeners", [])   # ticker registers its own listener at load
    ticker = load("dashboard/ticker")
    app, lab = tmp_path / "app", tmp_path / "lab"
    (app / "lab").mkdir(parents=True)
    (app / "lab" / "config.defaults.yaml").write_text("lab: {}\n")
    (lab / "lab").mkdir(parents=True)
    (lab / "lab" / "config.yaml").write_text("lab: {}\n")
    monkeypatch.setattr(ctx, "HUB", app)
    monkeypatch.setattr(ctx, "LAB", app / "lab")
    ctx.switch_hub(lab)
    assert ticker._SCHED_HUBS == {lab.resolve()}
