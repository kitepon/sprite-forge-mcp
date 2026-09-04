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
      card("ダメージ版", element("p", {}, "SAM 3.1 のマスクを使い、JoyAI 編集後に ToonOut で透過します。"), measurement({ "計測": "bbox 中心差・四隅 alpha", "出力": "透過 PNG" }))), results);
}

function settings(root) {
  const directions = ["正面", "右 45°", "右", "背面", "左", "左 45°"];
  const expressions = ["通常", "笑顔", "怒り", "驚き"];
  const costume = element("input", { placeholder: "例: 紺のローブ、teal の差し色" });
  const source = element("input", { placeholder: "素体候補の画像パスまたはID" });
  const name = element("input", { placeholder: "キャラクター名" });
  const desc = element("input", { placeholder: "説明（代名詞を含める。例: she/her, silver twin-tail idol）" });
  const styleRefs = element("input", { placeholder: "質感のネタ画像（パスを , 区切り、最大 5 枚）。質感はここから写す" });
  const result = element("div", { id: "bible-result", class: "muted" });
  const save = element("button", { onclick: async () => { try { result.textContent = "生成中…"; const job = await API.bible(source.value, name.value, desc.value, costume.value, styleRefs.value); state.activeJob = job.job_id; record("設定画", "設定画を生成", job.sheet_path || job.job_id, job.job_id); result.textContent = `完成: ${job.sheet_path} / ${job.html_path}`; notice("設定画を生成しました"); } catch (error) { notice(error.message, true); } } }, "設定画を生成");
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "設定画"), element("p", {}, "多方向・表情・衣装を選び、ジョブの進捗は過程画面で確認します。")),
    card("方向", element("div", { class: "chips" }, ...directions.map((name) => element("label", {}, element("input", { type: "checkbox", checked: name === "正面" }), name))), measurement({ "選択": "最大 6 方向", "モデル": "JoyAI-Image-Edit-Plus" })),
    card("表情と衣装", element("div", { class: "stack" }, element("div", { class: "chips" }, ...expressions.map((name) => element("label", {}, element("input", { type: "checkbox" }), name))), element("label", {}, "素体", source), element("label", {}, "名前", name), element("label", {}, "説明", desc), element("label", {}, "衣装", costume), element("label", {}, "質感のネタ", styleRefs), save, result)));
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
      const detail = element("small", { hidden: "hidden" }, value);
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
