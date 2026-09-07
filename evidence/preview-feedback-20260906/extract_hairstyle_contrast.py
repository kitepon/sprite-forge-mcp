"""髪型語彙の全スコアを比較し、NG固有の強さを省略せず出力する。"""
import argparse
import csv
from html import escape
import json
from pathlib import Path
from statistics import mean


HAIRSTYLES = '''long_hair short_hair hair_between_eyes very_long_hair twintails ponytail ahoge
braid medium_hair blunt_bangs hair_bun hair_over_one_eye parted_bangs twin_braids side_ponytail
floating_hair single_braid double_bun swept_bangs low_twintails hair_intakes wavy_hair bob_cut
drill_hair antenna_hair high_ponytail spiked_hair single_hair_bun straight_hair messy_hair
short_twintails hair_over_shoulder crossed_bangs low_ponytail side_braid short_hair_with_long_locks
hair_rings hair_flaps low-tied_long_hair short_ponytail curly_hair tentacle_hair hair_down
braided_ponytail asymmetrical_bangs long_bangs asymmetrical_hair hair_behind_ear
double-parted_bangs single_side_bun hair_spread_out very_short_hair crown_braid folded_ponytail
hime_cut hair_over_eyes flipped_hair absurdly_long_hair undercut bald hair_slicked_back
cone_hair_bun hair_up huge_ahoge side_braids low_twin_braids braided_bangs curtained_hair
hair_over_breasts braided_bun half_up_braid hair_pulled_back long_braid big_hair heart_ahoge
pointy_hair diagonal_bangs braided_hair_rings multi-tied_hair low-braided_long_hair front_ponytail
loose_hair_strand bow-shaped_hair short_bangs bangs_pinned_back parted_hair single_hair_intake
feather_hair center-flap_bangs long_hair_between_eyes quad_tails single_hair_ring hair_horns
hair_flowing_over mohawk dreadlocks buzz_cut high_side_ponytail afro arched_bangs bowl_cut
fiery_hair multiple_braids wide_ponytail choppy_bangs wolf_cut hair_ears side_up_bun
prehensile_hair donut_hair_bun side_ahoge expressive_hair sidecut tri_tails snake_hair
split_ponytail braided_sidelock ribbon_braid liquid_hair short_sidetail drill_ponytail lone_nape_hair
crystal_hair kishimen_hair fluffy_hair detached_ahoge wispy_bangs hair_on_horn bun_with_braided_base
folded_hair hair_vines fanged_bangs heart_hair cut_bangs pixie_cut tri_braids hair_over_face
hair_over_one_breast hair_between_breasts uneven_twintails sidelocks half_updo single_sidelock
updo drill_sidelocks low-tied_sidelocks long_sidelocks asymmetrical_sidelocks sidelocks_tied_back side_part'''.split()


def extract(report):
    scores = report['output']['scores']
    ng = report['selection']['selected_ng_numbers']
    comparison = [number for number in range(1, len(scores) + 1) if number not in ng]
    rows = []
    for tag in HAIRSTYLES:
        if tag not in scores[0]:
            raise ValueError(f'属性定義に存在しません：{tag}')
        values = [item[tag] for item in scores]
        ng_values = [values[number - 1] for number in ng]
        reference = [values[number - 1] for number in comparison]
        differences = {str(number): values[number - 1] - max(reference) for number in ng}
        rows.append({'tag': tag, 'ng_mean': mean(ng_values), 'comparison_mean': mean(reference),
                     'mean_difference': mean(ng_values) - mean(reference),
                     'ng_max': max(ng_values), 'comparison_max': max(reference),
                     'individual_excess': max(differences.values()),
                     'exceeding_ng_numbers': [int(number) for number, value in differences.items() if value > 0],
                     'per_ng_excess': differences, 'scores': values})
    rows.sort(key=lambda row: row['individual_excess'], reverse=True)
    return {'ng_numbers': ng, 'comparison_numbers': comparison, 'rows': rows,
            'definition': '個別超過量＝各NGスコア−比較7枚の最大スコア。最大の個別超過量順。群平均差も併記。閾値・上位件数で削除しない。'}


def save(output, result):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'contrast.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    weights = {'formula': 'max(0, NG画像のスコア - 比較7枚の最大スコア)',
               'margin': 0, 'normalized': False, 'images': []}
    weight_sections = []
    for number in result['ng_numbers']:
        features = [{'tag': row['tag'], 'weight': row['per_ng_excess'][str(number)],
                     'ng_score': row['scores'][number - 1], 'comparison_max': row['comparison_max']}
                    for row in result['rows'] if row['per_ng_excess'][str(number)] > 0]
        features.sort(key=lambda item: item['weight'], reverse=True)
        weights['images'].append({'number': number, 'features': features})
        weight_sections.append(f'<details><summary>NG {number}：{len(features)}属性の学習重み</summary><table>'
            '<tr><th>髪型属性</th><th>学習重み</th><th>NGスコア</th><th>比較最大</th></tr>'
            + ''.join(f'<tr><td>{escape(item["tag"])}</td><td>{item["weight"]:.8g}</td>'
                      f'<td>{item["ng_score"]:.8g}</td><td>{item["comparison_max"]:.8g}</td></tr>' for item in features)
            + '</table></details>')
    (output / 'weights.json').write_text(json.dumps(weights, ensure_ascii=False, indent=2))
    with (output / 'contrast.csv').open('w', newline='') as target:
        writer = csv.writer(target)
        writer.writerow(['tag', 'ng_mean', 'comparison_mean', 'mean_difference', 'ng_max', 'comparison_max', 'individual_excess', *range(1, 21)])
        for row in result['rows']:
            writer.writerow([row[key] for key in ('tag', 'ng_mean', 'comparison_mean', 'mean_difference', 'ng_max', 'comparison_max', 'individual_excess')] + row['scores'])
    rows = []
    for row in result['rows']:
        rows.append('<tr><td>' + escape(row['tag']) + '</td>' + ''.join(
            f'<td>{row[key]:.6g}</td>' for key in ('ng_max', 'comparison_max', 'individual_excess', 'mean_difference'))
            + '<td>' + ', '.join(map(str, row['exceeding_ng_numbers'])) + '</td></tr>')
    (output / 'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>NG固有の髪型特徴・全件比較</title><style>body{font:16px/1.7 sans-serif;margin:24px;background:#faf8f4}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #ccc}thead{background:#ddd}section{overflow:auto}</style>'
        '<h1>NGで強い髪型特徴を全件比較</h1><p>NG13枚と比較7枚。髪の長さ・形・束・結び方・前髪・配置を対象とし、髪色・飾り・衣装・体形・画風・動作は除外。</p>'
        f'<p>髪型属性{len(result["rows"])}件をすべて掲載。3語への要約やボブへの置き換えはしていません。</p>'
        '<p>NGの最大値から比較7枚の最大値を引いた差の大きい順です。17番など一部のNGだけに強い特徴も残ります。正の差は比較全画像を超えたNGがあることを示します。「存在しない」の断定ではありません。スコアは正答率ではありません。</p>'
        '<p>小さい差も削除せず掲載しています。微小値同士の差を強い検出と解釈しないため、絶対スコアも併記します。比較7枚を学習教材には使いません。今回は抽出のみです。</p>'
        '<p><a href="/api/file?path=ng-hairstyle-contrast-20260907/contrast.json">全スコアと画像別差分JSON</a> ／ <a href="/api/file?path=ng-hairstyle-contrast-20260907/contrast.csv">20枚の全比較CSV</a> ／ <a href="/api/file?path=ng-review-20-20260906/report.html">元画像20枚</a></p>'
        '<h2>今回使う学習重み</h2><p>重み = max(0, そのNG画像のスコア − 比較7枚の最大スコア)。追加余裕値0、正規化なし、上位件数制限なし。重みの計算完了であり、ESD学習の実行完了ではありません。</p>'
        '<p><a href="/api/file?path=ng-hairstyle-contrast-20260907/weights.json">画像別の学習重みJSON</a></p>'
        + ''.join(weight_sections)
        + '<h2>全属性の比較</h2><section><table><thead><tr><th>髪型属性</th><th>NG最大</th><th>比較最大</th><th>最大差</th><th>群平均差</th><th>比較最大を超えたNG番号</th></tr></thead><tbody>'
        + ''.join(rows) + '</tbody></table></section></html>')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    save(args.output, extract(json.loads(args.report.read_text())))
