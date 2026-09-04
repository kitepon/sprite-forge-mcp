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
  const form = element("form", { onsubmit: async (event) => {
    event.preventDefault(); start.disabled = true;
    try {
      const job = await API.startBase(prompt.value, seed.value);
      state.activeJob = job.job_id;
      record("素体", prompt.value || "素体生成", "ComfyUI に送信", job.job_id);
      location.hash = "#/process";
    } catch (error) { notice(`生成を開始できません: ${error.message}`, true); }
    finally { start.disabled = false; }
  }}, element("label", {}, "プロンプト", prompt), element("label", {}, "Seed", seed), start);
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "作業台"), element("p", {}, "生成・編集・ダメージ版を同じ記録へ送ります。")),
    element("div", { class: "cards" },
      card("素体", form, measurement({ "モデル": "Anima Turbo + LoRA", "計測": "生成後に記録" })),
      card("編集", element("p", {}, "JoyAI-Image-Edit-Plus で参照画像から多方向・表情・衣装を作成します。"), measurement({ "入力": "参照 1〜6 枚", "計測": "同一性・秒数" })),
      card("ダメージ版", element("p", {}, "SAM 3.1 のマスクを使い、JoyAI 編集後に ToonOut で透過します。"), measurement({ "計測": "bbox 中心差・四隅 alpha", "出力": "透過 PNG" }))));
}

function settings(root) {
  const directions = ["正面", "右 45°", "右", "背面", "左", "左 45°"];
  const expressions = ["通常", "笑顔", "怒り", "驚き"];
  const costume = element("input", { placeholder: "例: 紺のローブ、teal の差し色" });
  const save = element("button", { onclick: () => { record("設定画", "設定画の下書き", `衣装: ${costume.value || "未指定"}`); notice("設定画の下書きを記録しました"); } }, "下書きを記録");
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "設定画"), element("p", {}, "多方向・表情・衣装を選び、ジョブの進捗は過程画面で確認します。")),
    card("方向", element("div", { class: "chips" }, ...directions.map((name) => element("label", {}, element("input", { type: "checkbox", checked: name === "正面" }), name))), measurement({ "選択": "最大 6 方向", "モデル": "JoyAI-Image-Edit-Plus" })),
    card("表情と衣装", element("div", { class: "stack" }, element("div", { class: "chips" }, ...expressions.map((name) => element("label", {}, element("input", { type: "checkbox" }), name))), element("label", {}, "衣装", costume), save)));
}

function lora(root) {
  const dataset = element("input", { type: "file", multiple: "multiple", accept: "image/*" });
  const start = element("button", { onclick: () => { record("LoRA", "Anima LoRA 学習", `${dataset.files.length} 枚の教材を確認`); notice("学習開始の記録を追加しました"); } }, "学習を開始");
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "LoRA"), element("p", {}, "Anima Base v1.0 用の教材確認、学習進捗、成果物一覧です。")),
    card("教材確認", element("div", { class: "stack" }, element("label", {}, "教材画像", dataset), element("p", { class: "muted" }, "bf16 / rank 16 / alpha 16 / lr 1e-4"), start)),
    card("学習済み", element("p", {}, state.records.some((item) => item.kind === "LoRA") ? "ローカル記録に学習ジョブがあります。" : "まだ記録はありません。")));
}

function process(root) {
  const jobId = element("input", { placeholder: "ジョブ ID", value: state.activeJob || "" });
  const log = element("ol", { class: "event-log" }); let source;
  const disconnect = () => { source?.close(); source = null; };
  const connect = () => {
    disconnect(); log.replaceChildren(); state.events = [];
    if (!jobId.value) return notice("ジョブ ID を入力してください", true);
    source = API.events(jobId.value);
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
  if (!state.records.length) list.append(element("p", { class: "muted" }, "生成・設定画・LoRA の記録はまだありません。"));
  else state.records.forEach((item) => list.append(element("article", {}, element("strong", {}, item.kind), element("span", {}, item.title), element("small", {}, `${new Date(item.at).toLocaleString("ja-JP")} · ${item.detail}`))));
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "記録"), element("p", {}, "過去の生成、設定画、LoRA を端末ごとに辿れます。")), card("履歴", list));
}

const renderers = { workbench, settings, lora, process, records };
function route() {
  const route = location.hash.slice(2) || "workbench";
  const active = renderers[route] ? route : "workbench";
  renderNav(active); renderers[active]($("#app")); $("#app").focus();
}
async function gpu() {
  try { const value = await API.gpu(); $("#gpu").textContent = value.comfy_up ? "GPU 接続済み" : "GPU 未接続"; }
  catch { $("#gpu").textContent = "GPU 状態を取得できません"; }
}
window.addEventListener("hashchange", route);
route(); gpu();
