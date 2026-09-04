# p2-core — 新 backend core

## 実施内容

旧 backend の SDXL/Qwen/Mage-Flow、rembg/chroma、rpgdev adopt、WebSocket/SSE 再接続、
PowerShell 生成、SAM2 bridge を撤去した。Mac 側は HTTP 専用の `backend/comfy.py`、fox の
`C:\sf\train.py` を引数配列で SSH 起動する `backend/box.py`、UUID job と
`.cache/jobs/<id>.json` / `events.ndjson` を管理する `backend/events.py`、共通 use-case 層の
`backend/services.py` に分けた。

`backend/workflows.py` は採用済みの Anima Base、JoyAI Image Edit Plus、ToonOut、SAM 3.1
衣装マスク + JoyAI 編集 + `ImageCompositeMasked` の4経路を純粋な JSON builder として持つ。
設定は Anima/JoyAI/ToonOut/SAM 3.1 前提に絞り、Python 3.13 の `pyproject.toml` と `uv.lock` を
追加した。

## 最終試験と結果

1. `python3 -m compileall -q backend` は全 core module を成功としてコンパイルした。
2. 一時 event store へ同一 job の `queued` / `submitted` を追記し、`seq=1,2`、job JSON の
   保存・読出しを確認した。
3. Anima Base、JoyAI edit、ToonOut、SAM damage の4 builder を生成し、すべて非空 JSON graph かつ
   全 node に `class_type` があることを確認した。
4. `git diff --check` は成功した。

GPU を使う実走はこの core task の対象外であり、ComfyUI 通信は HTTP boundary として mocked test
可能な形に留めた。MCP/REST の薄層と WebUI は後続 task がこの services 層へ接続する。
