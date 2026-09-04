# p1-edit — 編集・設定画の新顔比較

## 実施内容

fox（ComfyUI 0.34.0 / RTX 5090）で、既存の
`.cache/generated/bible_firemage_panels/turn_front.png` を共通の人物参照として
Mage-Flow-Edit と JoyAI-Image-Edit-Plus の編集ベンチマークを行った。参照は
ComfyUI input の `p1_edit_firemage_front.png` としてアップロードした。

各モデルで次の12指示を1枚ずつ、768×1024・固定seedで生成した。

1. 正面、右前方45度、右側面、右後方45度、背面、左後方45度、左側面、左前方45度
2. neutral、smile、angry の表情
3. カジュアルな赤い旅装への衣装変更

Mage-Flow-Edit は int8 DiT、Qwen3-VL 4B、Mage VAE、30 steps / CFG 5 /
Euler-simple を使用した。JoyAI は int8 DiT、Qwen3-VL 8B int8、Wan VAE、30 steps /
CFG 4 / Euler-normal / CFGNorm pre-CFG を使用した。全出力は fox の
`ComfyUI/output/p1_edit/` に保存した。

## 最終試験と結果

1. Mage-Flow-Edit 正面の API workflow を `b41e6324-f336-42e3-a822-fae3fefb0736` として実行し、
   `mage_smoke_front_00001_.png` を出力した。成功、10.473秒。
2. JoyAI 正面の API workflow を `3b84678e-834b-4dfd-bab7-af184485cb73` として実行し、
   `joy_smoke_front_00001_.png` を出力した。成功、36.854秒。
3. 残る11指示を各モデルで連続実行した。Mage-Flow-Editは全11枚成功（4.690–6.780秒、
   平均4.940秒）、JoyAIは全11枚成功（29.784–36.598秒、平均30.677秒）。正面を含む
   12枚平均は Mage-Flow-Edit 5.401秒、JoyAI 31.192秒だった。
4. `/system_stats` で計測した常駐VRAMは Mage-Flow-Edit 14.22 GiB、JoyAI 25.94 GiB。
   どちらも OOM やキュー失敗なし。
5. 保存済みの全22比較出力と正面2枚を目視した。両モデルとも8方向・3表情・衣装変更で
   同一人物性を保ち、背面では顔を出さなかった。Mage-Flow-Editは王冠、赤いツインテール、
   炎衣装、杖の一貫性がより高く、JoyAIは側面の杖と衣装輪郭に揺れがあった。

受入条件である「8方向＋表情3種＋衣装1種を両モデルで生成」「同一人物性・後ろ姿・
1枚あたりの秒数・VRAMを比較」「`docs/09_modernization_bench.md` に勝者を記録」を満たす。
勝者は Mage-Flow-Edit とした。
