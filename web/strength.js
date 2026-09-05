import { API } from './api.js?v=studio-2';
import { h, field, button, action } from './ui.js?v=studio-2';

export function characterStrength(record) {
  const value = h('input', { type: 'number', min: 0, max: 2, step: 0.1, required: true,
    value: record.character_strength ?? 0.8, 'aria-label': 'キャラクターの特徴の強さ' });
  const status = h('p', { class: 'small', role: 'status' }, '保存済みの強さを表示しています。既定値は0.8です。');
  value.addEventListener('input', () => { status.textContent = '未保存です。保存後の新規生成から使います。'; });
  const root = h('fieldset', { class: 'strength-control stack' });
  const save = reset => {
    if (!reset && !value.reportValidity()) return;
    return action(root, async () => {
      const saved = await API.setCharacterStrength(record.name, reset ? 0.8 : Number(value.value));
      value.value = String(saved.character_strength);
      status.textContent = reset ? '既定値0.8に戻して保存しました。' : `強さ${saved.character_strength}を保存しました。`;
    });
  };
  root.append(field('キャラクターの特徴の強さ（研究中）', value,
    '弱めると衣装や構図の注文が通りやすくなる場合がありますが、顔や髪の再現も変わります。0ではキャラクターLoRAの影響をなくします。'),
    h('p', { class: 'muted small' }, 'このキャラクターの次のプレビュー・一枚絵・新しい設定画に使います。画風の強さは変えません。既存シートの部分描き直しは、生成時の強さを維持します。再学習は行いません。'),
    h('div', { class: 'actions' }, button('特徴の強さを保存', () => save(false), 'quiet'), button('既定値に戻す', () => save(true), 'quiet')), status);
  return root;
}
