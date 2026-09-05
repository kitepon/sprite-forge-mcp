# INSTALL — sprite-forge-mcp セットアップ

> このリポは**推論を持たない薄いオーケストレータ**。生成計算はすべて別マシンの **ComfyUI** が行う。「クローンして即生成」はできない＝**CUDA GPU で動く ComfyUI が必須**。以下はその前提で、他人（とそのAI）が自分の環境に立てるための手順。

## 前提（これが無いと動かない）
- **CUDA GPU で稼働する ComfyUI**（HTTP+WS で到達可能）。VRAM は **~30GB 目安（RTX 5090 級 32GB）**＝編集経路で DiT が ~24–27GB 常駐する。
- **必須モデル一式**を ComfyUI に配置（→ [docs/models.md](docs/models.md)）。
- **必須カスタムノード**：Qwen-Image-Edit ノード（`TextEncodeQwenImageEditPlus` 等）＋ Union ControlNet（`SetUnionControlNetType`）。ComfyUI は **0.25.0+** で検証済み（→ docs/models.md）。
- backend 用に **Python 3.11+**（`fastmcp` 要件）。

## 構成
- **backend**（FastAPI＋FastMCP・このリポ）＝制御マシンで動く（Mac/Linux/Windows どれでも可）。
- **ComfyUI**＝GPU マシンで動く。**同一マシンでも別マシンでも可**（backend は `SPRITEFORGE_COMFY_URL` で ComfyUI を指すだけ）。

## 1. GPU 側（ComfyUI）を用意
1. ComfyUI（0.25.0+）を導入。
2. 上記**必須カスタムノード**を入れる（Qwen-Image-Edit ノードセット／Union ControlNet サポート）。
3. [docs/models.md](docs/models.md) のモデルを**正確なファイル名で** `models/<サブフォルダ>/` に配置。
4. LAN 越しに使うなら ComfyUI を `0.0.0.0:8188` で公開（同一マシンなら不要）。
5. 確認：`curl http://<GPU_HOST>:8188/system_stats` が返る。`/object_info` に必須 class_type が在るか見るとノード不足を早期発見できる。

## 2. backend を立てる
```bash
git clone https://github.com/<you>/sprite-forge-mcp && cd sprite-forge-mcp
python3.12 -m venv .venv && . .venv/bin/activate     # 3.11+ 必須
pip install -r requirements.txt
cp .env.example .env                                  # 編集して下記を設定
uvicorn backend.app:app --host 127.0.0.1 --port 8765
```
`.env` で最低限：
- `SPRITEFORGE_COMFY_URL=http://<あなたのComfyUI>:8188`
- （採用を使うなら）`SPRITEFORGE_RPGDEV_SPRITES=/書き出し先/sprites`
- 全変数は [.env.example](.env.example) と `backend/config.py` を参照。`.env` は gitignore 済み。

## 3. 動作確認
- `curl localhost:8765/api/gpu` → `{"comfy_up":true,...}`。
- WebUI：ブラウザで `http://127.0.0.1:8765/` →「① 素体生成」で1枚出す。
- MCP：`http://127.0.0.1:8765/mcp/`（`.mcp.json` で Claude/Codex に URL 型 MCP 登録。初期化時に使い方マニュアルを返す）。

## 任意機能（無くてもコア＝生成/編集/バイブルは動く）
| 機能 | 要るもの |
|---|---|
| **SAM2 自動マスク** | `python3.12 -m venv .venv-sam2 && .venv-sam2/bin/pip install ultralytics`（任意・未導入でも手描きマスク可） |
| **コメント解釈** | ChatGPT契約でログイン済みの公式 `codex` CLI。下記の接続設定を使う。APIキーは不要 |
| **キャラ/画風 LoRA 学習** | GPU box に kohya **sd-scripts** ＋ accelerate/torch-CUDA。**※下記の制約参照** |
| **claude.ai/design 共有** | operator の claude.ai ログイン（任意・本体機能ではない） |

## コメント解釈の接続

バックエンドと同じ環境に公式Codex CLIとChatGPT契約のログインがあれば、接続用の環境変数は不要です。Dockerで動かす場合は、ログイン済みのサーバー本体へSSHで解釈を依頼できます。認証ファイルをコンテナへコピーする必要はありません。

サーバー本体にこのリポジトリと `uv` を配置し、`codex login status` が `Logged in using ChatGPT` を返すことを確認します。アプリが使うSSH公開鍵を指定して、サーバー本体で次を実行します。

```bash
python3 scripts/configure_intent_host.py \
  --root /absolute/path/to/sprite-forge-mcp \
  --public-key /absolute/path/to/app-key.pub \
  --authorized-keys /absolute/path/to/.ssh/authorized_keys
```

この処理は依存を導入し、既存のSSH登録を保存してから、指定鍵をコメント解釈コマンドに限定して登録します。同じ鍵が別用途で登録済みなら変更せず停止します。バックアップは指定したリポジトリ内の `.intent-setup-backups/` に保存します。

アプリの `.env` に `SPRITEFORGE_INTENT_SSH=user@cli-host` と `SPRITEFORGE_INTENT_HOST_ROOT=/absolute/path/to/sprite-forge-mcp` を設定します。SSH接続先と既知ホストは、コンテナへ渡す既存のSSH設定で管理します。配備後はWebUIから新しい注文を解釈し、確認案が返ることまで確かめてください。

試験用ディレクトリから本番へ切り替える時は、環境変数の変更に加えて、上のコマンドを本番の `--root` で再実行します。SSHで実行される配置はサーバーの鍵登録に固定されるためです。接続を撤回する時は、`authorized_keys` の末尾が `sprite-forge-intent` の登録行を取り除きます。他の登録を巻き戻さないよう、全体のバックアップ復元はその後の変更がない場合だけにします。

解釈処理はChatGPT契約ログインを指定し、APIキーの環境変数を除外します。認証失敗や利用上限はエラーで返し、別の課金経路へ切り替えません。

## 「何が無いと何が動くか」
| やりたいこと | 必須 |
|---|---|
| 素体生成 / ダメージ版編集 / キャラバイブル | ComfyUI＋モデル一式（**必須**） |
| 採用（rpgdev等へ書き出し） | `SPRITEFORGE_RPGDEV_SPRITES`（書き出し先ディレクトリ） |
| LoRA 学習 | GPU box の sd-scripts/accelerate（**現状 Windows 前提**） |
| SAM2 / AIプロンプト生成 / design共有 | それぞれ上表の任意セットアップ（無ければその機能だけ無効） |

## 正直な制約（盛らない）
- **LoRA 学習は現状 Windows box 前提**：`backend/training.py` が PowerShell/NSSM コマンドを生成し、box のパスを前提にする。**Linux/Mac の ComfyUI box では「学習だけ」動かない**（生成・編集・バイブルは OS 非依存で動く）。POSIX 対応は需要が出たら入れる予定。
- 長時間 GPU 学習で Windows のディスプレイが固まる場合は `TdrDelay=60`（レジストリ）＋再起動が要る（Windows 固有・Linux box は無関係）。
- モデルは各自で取得（→ docs/models.md）。リポにモデル重みは含めない。
- `adopt` は書き出し先へ**不可逆に上書き**する。設定先を確認してから使うこと。

詳しい設計は [docs/00_overview.md](docs/00_overview.md) から辿る。現在の作業規範と設計方針の正本は [AGENTS.md](AGENTS.md)。
