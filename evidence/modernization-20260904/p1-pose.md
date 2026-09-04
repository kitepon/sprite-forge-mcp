# p1-pose — 骨格参照によるポーズ指定の検証

## 実施内容

p1-base の勝者 Mage-Flow の出力を人物参照として、p1-edit の勝者
Mage-Flow-Edit へ黒い棒人間のキャスティング・ランジ骨格を第2参照として渡した。
Anima-Control-Pose preview-2 は Anima 素体を前提とするため、Mage-Flow が勝者となった
今回の素体選定には適用しなかった。

ComfyUI workflow `44fb4042-e642-4e80-9f53-ddbbec5dc620` は成功した。設定は
`mage_flow_edit_int8_convrot.safetensors`、Qwen3-VL 4B、Mage VAE、seed `2026090405`、
30 steps、CFG 5、Euler/simple で、`TextEncodeMageFlowEdit` の `image_1` に人物、
`image_2` に骨格を接続した。

## 最終試験と結果

1. ComfyUI の `execution_start` から `execution_success` まで 14.513 秒で成功し、
   `output/p1-pose/mage-flow-edit-skeleton_00001_.png`（1024×1024）を出力した。
2. 出力 SHA-256 は
   `eb22bf6a50ba5291024cc710f03b6eaf15675c8d1addbbd55c009a711a96d987`。人物参照は
   `200b1d8c2fc0402c08ede170a1b85985724f56670f6a9a80b5af7b4ba2b801f1`、骨格参照は
   `b1bdc60e93e059d163dbc097cc14ea16450416786d5e7f09b15b210ed8706cef` だった。
3. 目視では銀髪、teal/navy の外套、ブーツ、顔、金の杖という人物同一性は維持した。
   ただし骨格線と関節が画像へ直接残り、杖は縦のまま、人物本体はランジに再構成されなかった。

従って、Mage-Flow-Edit へ骨格を第2画像として渡すだけの方式は、同一性は一部維持しても
ポーズ追従と出力品質を同時には満たさず、不採用とした。詳細は
`docs/09_modernization_bench.md` の p1-pose 節に記録した。
