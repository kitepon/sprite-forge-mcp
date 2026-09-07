# NG指定と保持領域の予備実験結果

2026-09-07。指定確認は成立したが、今回の注意領域はNG部分の分離を確認できなかった。保持あり／なしの比較学習は未実行。元LoRAと本番台帳は変更していない。

- [指定確認6枚と全NG指摘](http://192.168.1.2:8766/api/file?path=ng-preservation-concepts-20260907/report.html)：2 seedそれぞれで通常指定・ボブ指定・長い後ろ髪指定を比較。指定した形状は描かれたが、顔の追加パネル等も増えた。通常指定2枚は前回同seed画像と画素単位で一致した。
- [定位診断2例の画像・注意領域・重ね合わせ](http://192.168.1.2:8766/api/file?path=ng-preservation-localize-20260907/report.html)：全6画像を掲載。診断実行12.91秒、更新なし。2例目には除去対象の長い後ろ髪が出ていない。hairという定位条件では残す結び髪も対象に入る。

観察の詳細は同梱のconcept-review.txtとlocalization-review.txt。元NG13枚は指摘別に対応付け、未選択7枚は未判定を維持した。この実験は保持方法の予備診断であり、学習後の改善率を示すものではない。

実装検証：ローカル全Python試験は306成功・6スキップ（8.42秒）。foxの注意取得・保持損失の試験は3成功。これらは計算と呼出しの検証であり、見た目の保持成立を意味しない。

再開に必要な実物はmain-serverの.cache/ng-preservation-concepts-20260907と.cache/ng-preservation-localize-20260907、foxのC:/sf/ng-preservation-localize-20260907。対応する回収済み画像と実行記録はローカルの同名.cacheディレクトリにある。比較器probe_preserve.pyのcompareはまだ実行しない。次の観測内容と未完了状態はLatticeの既存研究タスクへ記録する。

試作はRecelerの概念局所化を参考にしたAnima LoRA用の独自実装で、原論文の再現ではない。[著者実装](https://github.com/jasper0314-huang/Receler/blob/main/train_receler.py)は消去対象条件で潜在を生成し、その条件の注意を取得する。今回の通常指定による教師生成とhairによる定位は、そのまま同じ条件だと扱えない。
