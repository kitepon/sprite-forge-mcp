"""実教材とLoRA除去比較を公開用HTMLへまとめる。"""
import base64
from pathlib import Path

root = Path(__file__).parent / "private"
output = root / "lora-identity-v3"


def figure(label, path):
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<figure><figcaption>{label}</figcaption><img alt="{label}" src="data:image/png;base64,{data}"></figure>'


comparison = figure("LoRAあり・強度0.8", root / "identity-v1/after.png") + figure("LoRAなし・他条件は同じ", output / "without-lora.png")
materials = "".join(figure(f"学習画像 {i+1}／説明は呼び出し語のみ", root / f"lora-identity-v2/dataset_ndac1de01/{i:03d}.png") for i in range(4))
report = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>幼く見える原因の切り分け — Sprite Forge</title><style>body{max-width:1200px;margin:auto;padding:24px;font:16px/1.8 system-ui;background:#16202d;color:#edf4ff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}figure{margin:0}img{width:100%;border-radius:12px}a{color:#a7e5d1}h1{line-height:1.4}</style>
<h1>幼く見える原因の切り分け</h1><p>2026年9月6日・原因調査。再学習と本番設定の変更は行っていません。</p>
<h2>LoRAだけを外した実画像比較</h2><p>seed 1、1024×1024、Anima Base v1.0、28ステップ、CFG 4、Euler/simple。トリガー語を含む生成文・除外文は同一。追加画風LoRAなし。左は前回生成した実画像、右は今回生成。</p><div class="grid">''' + comparison + '''</div>
<h2>判定</h2><p>開発担当の目視では、LoRAなしでは幼い印象が弱まる一方、素材の絵柄と本人らしさも失われました。LoRAが顔・体格・絵柄を大きく変えていることは確認できました。単独seedで年齢感と絵柄の変化を分離できないため、LoRAだけが幼さの唯一の原因とは断定しません。LoRAを外すことは解決策として採用しません。</p>
<h2>実際に使われた学習教材</h2><p>学習job e5e22676-1683-4afe-bd37-8e6b4b8ebc35のdatasetと実行ログを読取りました。4枚すべての説明ファイルは、9バイトの呼び出し語 ndac1de01 のみ。年齢感、顔立ち、衣装、背景、構図の説明は入っていませんでした。画像自体からも学習するため、説明が無いことだけで原因確定とはしません。</p><div class="grid">''' + materials + '''</div>
<p>設定：Anima Base v1.0、rank/alpha 16、学習率1e-4、1200ステップ、各画像50回反復、6エポック、batch 1。解像度1024指定、実際のbucketは704×1024と1024×576。画像の構成は上半身2枚・顔アップ1枚・複数像の設定画1枚です。特定の設定値を不適切と断定する比較は未実施です。</p>
<h2>分かった範囲と次に試す内容</h2><p>現在のLoRAは、確認済みの詳細な教材説明を使って学習したものではありません。今回の生成文改善だけでは、その学習結果は変わりません。次の検証候補は、同じ4枚に素材の年齢感・顔立ち・身体比率・構図を説明し、利用者が確認した教材で別名のLoRAを学習して比較することです。旧LoRAを保持し、画像・学習設定・生成条件を同じにして説明の差を調べます。実行には学習の明示合意が必要です。</p>
<p>今回の調査では製品コード・台帳・既存LoRAを変更していません。Macの永続ターミナルからの接続は2回失敗し、別の実行経路で接続確認後に同じ診断を実行しました。</p><p><a href="/">スタジオへ</a></p></html>'''
(output / "lora-identity-diagnosis-20260906.html").write_text(report)
