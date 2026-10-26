from __future__ import annotations

from pathlib import Path

from backend.app.evaluation.golden import GoldenRunner, load_golden_set

ROOT = Path(__file__).resolve().parents[3]


def test_golden_set_has_ten_cases() -> None:
    cases = load_golden_set(ROOT / "golden_set.json")
    assert len(cases) == 10
    assert len({case.id for case in cases}) == 10
    assert all(case.prompt for case in cases)


async def test_golden_runner_calls_runner() -> None:
    cases = load_golden_set(ROOT / "golden_set.json")
    calls: list[str] = []

    async def runner(prompt: str) -> str:
        calls.append(prompt)
        return f"run-{len(calls)}"

    results = await GoldenRunner(cases).run_all(runner)
    assert len(results) == 10
    assert results[0]["run_id"] == "run-1"
    assert calls[0] == cases[0].prompt
