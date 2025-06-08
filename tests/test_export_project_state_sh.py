import os
import subprocess
from pathlib import Path
import tarfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_project_state.sh"


def run_script(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )


def test_full_export(tmp_path: Path) -> None:
    (tmp_path / "last_3_codex_diffs").mkdir()
    (tmp_path / "last_3_codex_diffs" / "patch.json").write_text("p")
    (tmp_path / "vault_export.json").write_text("{}")
    (tmp_path / "sim" / "results").mkdir(parents=True)
    (tmp_path / "sim" / "results" / "r.txt").write_text("r")
    strat_dir = tmp_path / "strategies" / "demo"
    strat_dir.mkdir(parents=True)
    strat_dir.joinpath("strategy.py").write_text('"""\nttl_hours: 24\n"""')
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "scoreboard.json").write_text('[{"pnl":1,"sharpe":2,"drawdown":0.1}]')

    env = os.environ.copy()
    env.update({
        "EXPORT_DIR": str(tmp_path / "export"),
        "PWD": str(tmp_path)
    })
    os.chdir(tmp_path)

    run_script([], env)

    archives = list((tmp_path / "export").glob("drp_export_FULL_*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0], "r:gz") as tar:
        names = tar.getnames()
        assert "./meta.json" in names
        assert "./strategy_ttl.txt" in names
        assert "./last_3_codex_diffs/patch.json" in names
        assert "./vault_export.json" in names
        assert "./results/r.txt" in names
        assert "./scoreboard.json" in names


def test_dry_run(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update({"EXPORT_DIR": str(tmp_path / "export"), "PWD": str(tmp_path)})
    os.chdir(tmp_path)
    result = run_script(["--dry-run"], env)
    assert "DRY RUN" in result.stdout
    assert not (tmp_path / "export").exists()
