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

function styleSelect(withNone = true) {
  const select = element("select", {}, withNone ? element("option", { value: "" }, "（画風なし＝キャラの LoRA だけ）") : "");
  API.styles().then((items) => items.forEach((item) => select.append(element("option", { value: item.name }, `${item.name}（${item.samples.length} 枚${item.lora_name ? "・学習済み" : "・未学習"}）`)))).catch(() => {});
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
  const style = styleSelect();
  const out = element("div", { class: "stack" });
  const go = element("button", { onclick: async () => { try { out.replaceChildren(element("p", { class: "muted" }, "生成中…")); const job = await API.fromBible(name.value, prompt.value, 1, style.value); record("シートから", prompt.value, job.path, job.job_id); out.replaceChildren(preview(job.path), element("p", { class: "muted" }, `${job.path} · ${job.elapsed_s}s`)); } catch (error) { notice(error.message, true); } } }, "キャラを描く");
  return card("キャラを描く（設定画の LoRA）", element("div", { class: "stack" }, element("label", {}, "キャラクター", name), element("label", {}, "指示（内容だけ。絵柄は LoRA）", prompt), element("label", {}, "画風", style), go, out));
}

function imageCard() {
  const prompt = element("textarea", { rows: "2", placeholder: "描いてほしい絵（例: a small fox on a snowy street）" });
  const style = styleSelect(false);
  const out = element("div", { class: "stack" });
  const go = element("button", { onclick: async () => { try { out.replaceChildren(element("p", { class: "muted" }, "生成中…")); const job = await API.image(prompt.value, style.value); record("画風だけで", prompt.value, job.path, job.job_id); out.replaceChildren(preview(job.path), element("p", { class: "muted" }, `${job.path} · ${job.elapsed_s}s`)); } catch (error) { notice(error.message, true); } } }, "画風だけで描く");
  return card("画風だけで描く（画風 LoRA）", element("div", { class: "stack" }, element("label", {}, "指示", prompt), element("label", {}, "画風", style), go, out));
}

function settings(root) {
  // Three stages, each of which stops so the owner can look and correct before the next.
  const name = element("input", { placeholder: "キャラクター名" });
  const current = element("div", { class: "stack" });
  const show = async () => {
    try {
      const c = await API.character(name.value);
      const rows = c.samples.map((s) => {
        const cap = element("input", { value: s.caption || "", placeholder: "この絵の説明（衣装など）" });
        return element("div", { class: "actions" }, element("img", { src: API.file(s.path), class: "thumb" }), element("span", { class: "muted" }, `#${s.index}`), cap,
          element("button", { class: "quiet", onclick: async () => { await API.setCaption(name.value, s.index, cap.value); notice("説明を保存"); } }, "保存"),
          element("button", { class: "quiet", onclick: async () => { await API.removeSample(name.value, s.index); show(); } }, "外す"));
      });
      current.replaceChildren(element("p", { class: "muted" }, `trigger: ${c.trigger} · LoRA: ${c.lora_name || "未学習"} · 画風: ${c.style || "なし"} · 設定画: ${c.bible?.sheet_path || "未作成"}`), ...rows, c.samples_sheet ? preview(c.samples_sheet) : "");
    } catch (error) { current.replaceChildren(element("p", { class: "muted" }, error.message)); }
  };
  name.addEventListener("change", show);
  // stage 1
  const desc = element("input", { placeholder: "説明（代名詞を含める。例: she/her, silver twin-tail idol）" });
  const attr = element("input", { placeholder: "属性メモ（シートの見出し）" });
  const create = element("button", { onclick: async () => { try { await API.createCharacter(name.value, desc.value, attr.value); notice("キャラクターを作成"); show(); } catch (error) { notice(error.message, true); } } }, "① キャラクターを作る");
  const images = picker("サンプル画像（複数可）");
  const captions = element("input", { placeholder: "画像ごとの説明を | 区切りで（任意）" });
  const add = element("button", { onclick: async () => { try { await API.addSamples(name.value, images.value, captions.value); notice("サンプルを追加"); show(); } catch (error) { notice(error.message, true); } } }, "サンプルを追加");
  // stage 2
  const steps = element("input", { type: "number", value: "1200", min: "1" });
  const trainOut = element("p", { class: "muted" });
  const train = element("button", { onclick: async () => { try { trainOut.textContent = "学習中（約 15 分）…過程画面で進捗"; const job = await API.train(name.value, steps.value); state.activeJob = job.job_id; trainOut.textContent = `完了: ${job.lora_name}`; record("LoRA", name.value, job.lora_name, job.job_id); show(); } catch (error) { notice(error.message, true); } } }, "② LoRA を学習する");
  const style = styleSelect();
  const setStyle = element("button", { class: "quiet", onclick: async () => { try { await API.setCharacterStyle(name.value, style.value); notice(style.value ? `画風 ${style.value} を設定` : "画風を外した"); show(); } catch (error) { notice(error.message, true); } } }, "この画風をキャラに設定");
  const ptags = element("input", { value: "full body, standing, front view, looking at viewer", placeholder: "プレビューの内容" });
  const pseed = element("input", { type: "number", value: "1", min: "0" });
  const pout = element("div", { class: "stack" });
  const prev = element("button", { onclick: async () => { try { pout.replaceChildren(element("p", { class: "muted" }, "数秒…")); const job = await API.previewCharacter(name.value, ptags.value, pseed.value, 2); pout.replaceChildren(...job.pictures.map((p) => preview(p.path))); } catch (error) { notice(error.message, true); } } }, "プレビュー 2 枚");
  // stage 3
  const bseed = element("input", { type: "number", value: "1", min: "0" });
  const bout = element("div", { class: "stack" });
  const make = element("button", { onclick: async () => { try { bout.replaceChildren(element("p", { class: "muted" }, "23 パネル生成（約 3 分）…")); const job = await API.bible(name.value, bseed.value); state.activeJob = job.job_id; record("設定画", name.value, job.sheet_path, job.job_id); bout.replaceChildren(preview(job.sheet_path), element("p", { class: "muted" }, `${job.sheet_path} / ${job.html_path}`)); show(); } catch (error) { notice(error.message, true); } } }, "③ 設定画を作る");
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "設定画"), element("p", {}, "① サンプルを集めて直す → ② LoRA を学習してプレビューで確かめる → ③ 設定画を作り、パネルを言葉で直す。各段で止まる。")),
    card("キャラクター", element("div", { class: "stack" }, element("label", {}, "名前", name), current)),
    card("① サンプル", element("div", { class: "stack" }, element("label", {}, "説明", desc), element("label", {}, "属性", attr), create, element("label", {}, "画像", images.node), element("label", {}, "画像ごとの説明", captions), add)),
    card("② LoRA とプレビュー", element("div", { class: "stack" }, element("label", {}, "step 数", steps), train, trainOut, element("label", {}, "画風（別の画像から学習した画風 LoRA を重ねる）", style), setStyle, element("label", {}, "プレビューの内容", ptags), element("label", {}, "Seed", pseed), prev, pout)),
    card("③ 設定画", element("div", { class: "stack" }, element("label", {}, "Seed", bseed), make, bout)),
    redrawCard(name),
    styleCard());
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

function styleCard() {
  // A style = pictures → a style LoRA. Usage 4 (a saved look) and the source of usages 2 and 5.
  const name = element("input", { placeholder: "画風名" });
  const note = element("input", { placeholder: "自分用メモ（任意）" });
  const images = picker("画風の画像（複数）");
  const captions = element("input", { placeholder: "画像ごとの説明を | 区切りで（任意。何が写っているか）" });
  const steps = element("input", { type: "number", value: "1200", min: "1" });
  const list = element("div", { class: "stack" });
  const draw = () => API.styles().then((items) => list.replaceChildren(...(items.length ? items.map((item) => element("div", { class: "actions" }, element("strong", {}, item.name), element("span", { class: "muted" }, `${item.samples.length} 枚 · ${item.lora_name || "未学習"} ${item.note || ""}`), element("button", { class: "quiet", onclick: async () => { await API.deleteStyle(item.name); draw(); } }, "削除"))) : [element("p", { class: "muted" }, "まだありません")]))).catch(() => {});
  draw();
  const create = element("button", { onclick: async () => { try { await API.createStyle(name.value, note.value); notice(`画風 ${name.value} を作成`); draw(); } catch (error) { notice(error.message, true); } } }, "画風を作る");
  const add = element("button", { onclick: async () => { try { await API.addStyleSamples(name.value, images.value, captions.value); notice("画像を追加"); draw(); } catch (error) { notice(error.message, true); } } }, "画像を追加");
  const out = element("p", { class: "muted" });
  const train = element("button", { onclick: async () => { try { out.textContent = "学習中（約 15 分）…"; const job = await API.trainStyle(name.value, steps.value); out.textContent = `完了: ${job.lora_name}`; draw(); } catch (error) { notice(error.message, true); } } }, "画風 LoRA を学習する");
  return card("画風（画像から学習する画風 LoRA）", element("div", { class: "stack" }, element("label", {}, "名前", name), element("label", {}, "メモ", note), create, element("label", {}, "画像", images.node), element("label", {}, "画像ごとの説明", captions), add, element("label", {}, "step 数", steps), train, out, list));
}

function lora(root) {
  const dataset = element("input", { placeholder: "キャラクター名（設定画画面で作ったもの）" });
  const progress = element("p", { id: "lora-progress", class: "muted" }, "未開始");
  const trained = element("p", { id: "lora-list" }, "読み込み中");
  API.loras().then((items) => { trained.textContent = items.join(", ") || "まだありません"; });
  const start = element("button", { onclick: async () => { try { progress.textContent = "学習中…"; const job = await API.train(dataset.value); state.activeJob = job.job_id; record("LoRA", "Anima LoRA 学習", job.lora_name, job.job_id); progress.textContent = `完了 ${job.progress?.step || job.steps}/${job.progress?.total || job.steps}: ${job.lora_name}`; trained.textContent = [...new Set([trained.textContent, job.lora_name])].join(", "); notice("学習を完了しました"); } catch (error) { notice(error.message, true); } } }, "学習を開始");
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "LoRA"), element("p", {}, "Anima Base v1.0 用の教材確認、学習進捗、成果物一覧です。")),
    card("教材確認", element("div", { class: "stack" }, element("label", {}, "キャラクター名", dataset), element("p", { class: "muted" }, "bf16 / rank 16 / alpha 16 / lr 1e-4 / 教材はキャラクターのサンプル"), start, progress)), card("学習済み", trained));
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
