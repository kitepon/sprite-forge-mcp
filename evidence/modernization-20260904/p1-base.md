# p1-base — 素体生成の新顔比較

## 実施内容

fox（ComfyUI 0.34.0 / RTX 5090）で、Anima Base v1.0、Mage-Flow int8、
Krea 2 raw int8 を同一の JRPG キャラクター指示で各 4 枚、1024×1024・
seed `2026090401`–`2026090404` により生成した。比較結果は
`docs/09_modernization_bench.md` の「素体生成」節に記録した。

## 最終試験と結果

1. ComfyUI API の各候補 workflow を 4 回ずつ実行し、Anima、Mage-Flow、Krea 2 とも
   4/4 の画像出力に成功した。
2. ComfyUI の `execution_start` から `execution_success` の差を計測した。平均は
   Anima 6.65 秒、Mage-Flow 3.71 秒、Krea 2 3.96 秒だった。
3. 保存済みの 12 画像を目視し、Mage-Flow は 4/4 で全身・正面・銀髪・teal/navy 配色・
   杖・淡色背景を保ち、最も明瞭な輪郭だった。Anima は 2/4、Krea 2 は軟焦点・小物混入・
   頭部潰れのため素体用途には劣った。
4. 各候補の代表画像への絶対パスと残る 3 枚の保存規則をベンチマーク文書へ記し、
   勝者を Mage-Flow と一意に決定した。

受入条件である Anima / Mage-Flow / Krea 2 の各 4 枚比較、画像パス付きの
`docs/09_modernization_bench.md` への記録、および単一の勝者決定を満たす。
