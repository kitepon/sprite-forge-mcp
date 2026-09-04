# p1-damage — SAM 3.1 衣装マスクによるダメージ版

## 実施内容

前担当の fox / ComfyUI 実行履歴を引き継ぎ、`p1_damage_firemage_base.png` に対して
SAM 3.1 Multiplex の `character` と `red robe clothing` テキストマスク、Mage-Flow-Edit、
`ImageCompositeMasked` によるマスク外復元を確認した。編集器は
`mage_flow_edit_int8_convrot.safetensors`、Qwen3-VL 4B、Mage VAE、seed 41002、30 steps、
CFG 5、Euler/simple を使用した。

主 workflow `a9e743c0-c13f-49f9-b706-06537d82cdb4` は成功し、実行時間は 10.169 秒だった。
`f33a5343-5321-4dbd-9b49-43850b02ff72` は character / clothing の SAM 3.1 マスク出力を
成功として記録している。

## 最終試験と結果

fox から保存済み input、raw、composited RGBA、character mask、clothing mask を取得し、
768×1024 の画素配列として検証した。

1. `firemage-damaged-composited_00001_.png` の四隅 alpha はすべて 0 だった。
2. base と composited の RGB 差分は衣装マスク内に 410,546 px あり、衣装マスク外は 0 px
   だった。従って顔・髪・王冠・手・杖・背景を含むマスク外は pixel-exact に復元されている。
3. 白背景を除く RGB < 250 のシルエット bbox 中心差は x -7.0 px、y +0.5 px だった。
   これは計画どおり記録値であり、受入 gate には用いない。
4. 合成画像を目視し、赤いローブと袖の焦げ・破れが確認でき、人物の顔、髪、王冠、手、杖は
   維持されていた。

最終 RGBA の SHA-256 は
`020dbecaafc62ed67ebbf0258fd3d2a47c52502614aba78d3eba70753ccd3dc5` である。`docs/09_modernization_bench.md`
に入力、workflow、出力位置、測定値を記録した。 
