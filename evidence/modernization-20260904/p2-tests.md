# p2-tests — GPU 非依存の受入テスト

## 実施内容

- CI を `compileall` だけの構文確認から Python 3.13 の `pytest` 実行へ置き換えた。
- `pyproject.toml` の development dependency group に `pytest>=8.0` を追加し、
  `uv.lock` を更新した。
- GPU や fox へ接続しない4ファイル・12テストを追加した。
  - `test_events.py`: job ごとの連番、NDJSON 保存、job state 保存、壊れた行の無視。
  - `test_workflows.py`: Anima / JoyAI / ToonOut / damage の JSON graph 形、seed・寸法、
    damage の衣装マスク外復元接続。
  - `test_box.py`: SSH / SCP が PowerShell や shell 文字列を作らない引数ベクタで、
    bf16・rank 16・alpha 16 を渡すこと。
  - `test_audit.py`: service の queued → submitted → success 遷移と event 記録、
    未知 job の応答。

## 検証

隔離 worktree を明示した `PYTHONPATH` で次を実行した。

```text
PYTHONPATH=<worktree> uv run --offline --directory <worktree> pytest -q <worktree>/tests
```

結果は **12 passed in 0.06s**。初回は呼び出し cwd が canonical 側に残り `backend` が
探索されず collection error となったため、上記の worktree 明示に修正して成功した。
検証で作られた `.venv`、`.pytest_cache`、`__pycache__` は worktree の観測対象に残さず
`/tmp` へ退避した。
