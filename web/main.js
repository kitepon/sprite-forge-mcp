import { API } from "./api.js";
import { state } from "./state.js";
import { $, card, element, notice } from "./ui.js";

const routes = [["workbench", "作業台"], ["settings", "設定画"], ["lora", "LoRA"], ["process", "過程"], ["records", "記録"]];

function record(kind, title, detail, id = crypto.randomUUID()) {
  const value = { id, kind, title, detail, at: new Date().toISOString() };
  state.save(value);
  return value;
}

function renderNav(active) {
  const nav = $("#nav"); nav.replaceChildren(...routes.map(([route, label]) =>
    element("a", { href: `#/${route}`, class: route === active ? "active" : "" }, label)));
}

function picker(placeholder, multiple = true) {
  // A text field of picture paths (comma-separated) plus a file input that uploads and fills it in.
  const text = element("input", { placeholder });
  const file = element("input", { type: "file", accept: "image/*", ...(multiple ? { multiple: "multiple" } : {}), onchange: async () => {
    try { const stored = await API.upload(file.files); const paths = stored.map((item) => item.path); text.value = multiple && text.value ? `${text.value},${paths.join(",")}` : paths.join(","); notice(`${paths.length} 枚を取り込みました`); }
    catch (error) { notice(`取り込めません: ${error.message}`, true); }
  } });
  return { node: element("div", { class: "stack" }, text, file), get value() { return text.value; } };
}

function presetSelect() {
  const select = element("select", {}, element("option", { value: "" }, "（プリセットなし）"));
  API.presets().then((items) => items.forEach((item) => select.append(element("option", { value: item.name }, `${item.name}（${item.images.length} 枚）`)))).catch(() => {});
  return select;
}

function preview(path) {
  return path ? element("img", { src: API.file(path), alt: path, class: "preview" }) : element("span", { class: "muted" }, "");
}

function measurement(values) {
  return element("dl", { class: "measurements" }, ...Object.entries(values).flatMap(([key, value]) => [element("dt", {}, key), element("dd", {}, value)]));
}

function workbench(root) {
  const prompt = element("textarea", { name: "prompt", rows: "3", placeholder: "例: 銀髪の見習い魔法使い、正面、白背景" });
  const seed = element("input", { type: "number", name: "seed", value: "1", min: "0" });
  const start = element("button", { type: "submit" }, "素体を生成");
  const results = element("div", { id: "candidate-results", class: "stack" });
  const form = element("form", { onsubmit: async (event) => {
    event.preventDefault(); start.disabled = true;
    try {
      const job = await API.sprite(prompt.value, seed.value);
      state.activeJob = job.job_id;
      record("素体", prompt.value || "素体生成", `${job.candidates?.length || 0}候補を生成`, job.job_id);
      results.replaceChildren(...(job.candidates || []).map((candidate) => {
        const status = element("p", { class: "muted" }, JSON.stringify(candidate.canvas || {}));
        const transparent = element("button", { onclick: async () => { const value = await API.transparent(candidate.path); status.textContent = `透過: ${value.path}`; } }, "透過");
        const pixel = element("button", { onclick: async () => { const value = await API.pixelize(candidate.path); status.textContent = `ドット化: ${value.path}`; } }, "ドット化");
        return card(`候補 ${candidate.seed || ""}`, element("div", { class: "stack" }, status, element("div", { class: "actions" }, transparent, pixel)));
      }));
    } catch (error) { notice(`生成を開始できません: ${error.message}`, true); }
    finally { start.disabled = false; }
  }}, element("label", {}, "プロンプト", prompt), element("label", {}, "Seed", seed), start);
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "作業台"), element("p", {}, "生成・編集・ダメージ版を同じ記録へ送ります。")),
    element("div", { class: "cards" },
      card("素体", form, measurement({ "モデル": "Anima Turbo + LoRA", "計測": "生成後に記録" })),
      card("編集", element("p", {}, "JoyAI-Image-Edit-Plus で参照画像から多方向・表情・衣装を作成します。"), measurement({ "入力": "参照 1〜6 枚", "計測": "同一性・秒数" })),
      card("ダメージ版", element("p", {}, "SAM 3.1 のマスクを使い、JoyAI 編集後に ToonOut で透過します。"), measurement({ "計測": "bbox 中心差・四隅 alpha", "出力": "透過 PNG" })),
      fromBibleCard(), imageCard()), results);
}

function fromBibleCard() {
  const name = element("input", { placeholder: "設定画の名前（例: Bell）" });
  const prompt = element("textarea", { rows: "2", placeholder: "描いてほしい絵（例: waving on a stage, spotlight）" });
  const out = element("div", { class: "stack" });
  const go = element("button", { onclick: async () => { try { out.replaceChildren(element("p", { class: "muted" }, "生成中…")); const job = await API.fromBible(name.value, prompt.value); record("シートから", prompt.value, job.path, job.job_id); out.replaceChildren(preview(job.path), element("p", { class: "muted" }, `${job.path} · ${job.elapsed_s}s`)); } catch (error) { notice(error.message, true); } } }, "シートから描く");
  return card("シートから描く", element("div", { class: "stack" }, element("label", {}, "設定画", name), element("label", {}, "指示（内容だけ。絵柄は LoRA）", prompt), go, out));
}

function imageCard() {
  const prompt = element("textarea", { rows: "2", placeholder: "描いてほしい絵（例: a small fox on a snowy street）" });
  const preset = presetSelect();
  const refs = picker("質感のネタ画像");
  const out = element("div", { class: "stack" });
  const go = element("button", { onclick: async () => { try { out.replaceChildren(element("p", { class: "muted" }, "生成中…")); const job = await API.image(prompt.value, preset.value, refs.value); record("質感だけで", prompt.value, job.path, job.job_id); out.replaceChildren(preview(job.path), element("p", { class: "muted" }, `${job.path} · ${job.elapsed_s}s`)); } catch (error) { notice(error.message, true); } } }, "質感だけで描く");
  return card("質感だけで描く", element("div", { class: "stack" }, element("label", {}, "指示", prompt), element("label", {}, "質感プリセット", preset), element("label", {}, "質感のネタ", refs.node), go, out));
}

function settings(root) {
  const images = picker("キャラクターの画像（複数可。この絵柄と本人を LoRA が覚える）");
  const name = element("input", { placeholder: "キャラクター名（trigger 語にもなる）" });
  const desc = element("input", { placeholder: "説明（代名詞を含める。例: she/her, silver twin-tail idol, white and gold outfit）" });
  const captions = element("input", { placeholder: "画像ごとの説明を | 区切りで（任意。衣装が違う画像を分けて覚えさせる）" });
  const costume = element("input", { placeholder: "属性メモ（シートの見出しに載る）" });
  const lora = element("input", { placeholder: "学習済み LoRA 名（任意。あれば学習を飛ばす）" });
  API.loras().then((items) => { lora.setAttribute("list", "lora-list"); root.append(element("datalist", { id: "lora-list" }, ...items.map((item) => element("option", { value: item })))); }).catch(() => {});
  const result = element("div", { class: "stack" });
  const save = element("button", { onclick: async () => { try { result.replaceChildren(element("p", { class: "muted" }, "LoRA 学習（約 15 分）→ 23 パネル生成。過程画面で進捗が見られる")); const job = await API.bible(images.value, name.value, desc.value, costume.value, lora.value, captions.value); state.activeJob = job.job_id; record("設定画", name.value || "設定画を生成", job.sheet_path || job.job_id, job.job_id); result.replaceChildren(preview(job.sheet_path), element("p", { class: "muted" }, `${job.sheet_path} / ${job.html_path} · LoRA ${job.lora_name}`)); notice("設定画を生成しました"); } catch (error) { notice(error.message, true); } } }, "設定画を生成");
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "設定画"), element("p", {}, "持ってきた画像で LoRA を学習し、その LoRA で方向・表情・衣装・ちび・装備の 23 パネルを描きます。絵柄は画像から学ぶので、言葉では指定しません。")),
    card("設定画を作る", element("div", { class: "stack" }, element("label", {}, "画像", images.node), element("label", {}, "名前", name), element("label", {}, "説明", desc), element("label", {}, "画像ごとの説明", captions), element("label", {}, "属性", costume), element("label", {}, "LoRA", lora), save, result)),
    redrawCard(name),
    presetCard());
}

function redrawCard(nameInput) {
  // Review-and-adjust: pick any panel of a finished bible, say what it should be, redraw it.
  const target = element("input", { placeholder: "設定画名（空なら上の名前）" });
  const panel = element("select", {});
  const tags = element("textarea", { rows: "2", placeholder: "内容の言葉（空ならそのパネルの既定。例: ball gown, floor-length dress, elbow gloves, no frills）" });
  const seed = element("input", { type: "number", value: "1", min: "0" });
  const avoid = element("input", { placeholder: "避ける言葉（例: frills, boots）。「no ○○」は効かないのでこちらへ" });
  const out = element("div", { class: "stack" });
  API.panels().then((items) => { panel.replaceChildren(...items.map((item) => element("option", { value: item.key, "data-tags": item.tags }, `${item.section} / ${item.label}`))); tags.placeholder = panel.selectedOptions[0]?.dataset.tags || tags.placeholder; }).catch(() => {});
  panel.addEventListener("change", () => { tags.placeholder = panel.selectedOptions[0]?.dataset.tags || ""; });
  const go = element("button", { onclick: async () => { try { out.replaceChildren(element("p", { class: "muted" }, "描き直し中…")); const job = await API.redraw(target.value || nameInput.value, panel.value, tags.value, seed.value, avoid.value); record("描き直し", `${job.name} / ${job.panel}`, job.path, job.job_id); out.replaceChildren(preview(job.path), element("p", { class: "muted" }, `${job.prompt} · ${job.elapsed_s}s · シート更新: ${job.sheet_path}`)); } catch (error) { notice(error.message, true); } } }, "このパネルを描き直す");
  return card("パネルを描き直す（見て、指示して、直す）", element("div", { class: "stack" }, element("label", {}, "設定画", target), element("label", {}, "パネル", panel), element("label", {}, "言葉", tags), element("label", {}, "避ける言葉", avoid), element("label", {}, "Seed", seed), go, out));
}

function presetCard() {
  const name = element("input", { placeholder: "プリセット名" });
  const images = picker("プリセットにする画像（複数）");
  const note = element("input", { placeholder: "自分用メモ（任意）" });
  const list = element("div", { class: "stack" });
  const draw = () => API.presets().then((items) => list.replaceChildren(...(items.length ? items.map((item) => element("div", { class: "actions" }, element("strong", {}, item.name), element("span", { class: "muted" }, `${item.images.length} 枚 ${item.note || ""}`), element("button", { class: "quiet", onclick: async () => { await API.deletePreset(item.name); draw(); } }, "削除"))) : [element("p", { class: "muted" }, "まだありません")]))).catch(() => {});
  draw();
  const save = element("button", { onclick: async () => { try { await API.savePreset(name.value, images.value, note.value); notice(`プリセット ${name.value} を保存しました`); draw(); } catch (error) { notice(error.message, true); } } }, "プリセットを保存");
  return card("質感プリセット", element("div", { class: "stack" }, element("label", {}, "名前", name), element("label", {}, "画像", images.node), element("label", {}, "メモ", note), save, list));
}

function lora(root) {
  const dataset = element("input", { placeholder: "設定画名 (例: Azure Mage)" });
  const progress = element("p", { id: "lora-progress", class: "muted" }, "未開始");
  const trained = element("p", { id: "lora-list" }, "読み込み中");
  API.loras().then((items) => { trained.textContent = items.join(", ") || "まだありません"; });
  const start = element("button", { onclick: async () => { try { progress.textContent = "学習中…"; const job = await API.train(dataset.value); state.activeJob = job.job_id; record("LoRA", "Anima LoRA 学習", job.lora_name, job.job_id); progress.textContent = `完了 ${job.progress?.step || job.steps}/${job.progress?.total || job.steps}: ${job.lora_name}`; trained.textContent = [...new Set([trained.textContent, job.lora_name])].join(", "); notice("学習を完了しました"); } catch (error) { notice(error.message, true); } } }, "学習を開始");
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "LoRA"), element("p", {}, "Anima Base v1.0 用の教材確認、学習進捗、成果物一覧です。")),
    card("教材確認", element("div", { class: "stack" }, element("label", {}, "設定画名", dataset), element("p", { class: "muted" }, "bf16 / rank 16 / alpha 16 / lr 1e-4"), start, progress)), card("学習済み", trained));
}

function process(root) {
  const jobId = element("input", { placeholder: "ジョブ ID", value: state.activeJob || "" });
  const log = element("ol", { class: "event-log" }); let source;
  const disconnect = () => { source?.close(); source = null; };
  const connect = () => {
    disconnect(); log.replaceChildren(); state.events = [];
    if (!jobId.value) return notice("ジョブ ID を入力してください", true);
    source = API.events();
    source.onmessage = (event) => {
      const value = JSON.parse(event.data); state.events.push(value);
      log.append(element("li", {}, `#${value.seq} ${value.kind} — ${value.at}`));
    };
    source.onerror = () => { disconnect(); notice("このジョブの SSE 接続を待機しています"); };
    notice("このジョブだけの events.ndjson ストリームを購読中です");
  };
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "過程"), element("p", {}, "ジョブ ID ごとの SSE だけを読み、他ジョブのイベントは表示しません。")),
    card("events.ndjson", element("div", { class: "stack" }, element("label", {}, "ジョブ ID", jobId), element("div", { class: "actions" }, element("button", { onclick: connect }, "購読"), element("button", { class: "quiet", onclick: disconnect }, "停止")), log)));
}

function records(root) {
  const list = element("div", { class: "records" });
  const draw = (items) => {
    list.replaceChildren();
    if (!items.length) return list.append(element("p", { class: "muted" }, "生成・設定画・LoRA の記録はまだありません。"));
    items.forEach((item) => {
      const kind = item.kind || "job";
      const title = item.title || item.name || item.bible_name || item.job_id;
      const value = item.detail || `${item.status || "unknown"} · ${item.lora_name || item.sheet_path || item.candidates?.[0]?.path || item.job_id}`;
      const picture = item.sheet_path || item.path || item.candidates?.[0]?.path || item.detail;
      const detail = element("small", { hidden: "hidden" }, value, typeof picture === "string" && /\.png$/.test(picture) ? preview(picture) : "");
      list.append(element("article", {}, element("strong", {}, kind), element("span", {}, title), element("button", { class: "quiet", onclick: () => detail.removeAttribute("hidden") }, "詳細"), detail));
    });
  };
  draw(state.records);
  API.jobs().then((jobs) => {
    const localIds = new Set(state.records.map((item) => item.id));
    draw([...jobs.filter((job) => !localIds.has(job.job_id)), ...state.records]);
  }).catch((error) => notice(`サーバー記録を取得できません: ${error.message}`, true));
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "記録"), element("p", {}, "過去の生成、設定画、LoRA を端末ごとに辿れます。")), card("履歴", list));
}

const renderers = { workbench, settings, lora, process, records };
function route() {
  const route = location.hash.slice(2) || "workbench";
  const active = renderers[route] ? route : "workbench";
  renderNav(active); renderers[active]($("#app")); $("#app").focus();
}
async function gpu() {
  try {
    const value = await API.gpu();
    const connected = value.comfy_up ?? Boolean(value.devices?.length);
    $("#gpu").textContent = connected ? "GPU 接続済み" : "GPU 未接続";
  }
  catch { $("#gpu").textContent = "GPU 状態を取得できません"; }
}
window.addEventListener("hashchange", route);
route(); gpu();
