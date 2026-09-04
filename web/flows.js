// Guided flows: pick what you want to do, then walk the steps. Each step stops so you can look
// and correct before the next (and the expensive ones — training — only run when you press them).
import { API } from "./api.js";
import { state } from "./state.js";
import { card, element, notice } from "./ui.js";

export const FLOWS = [
  { id: "sheet", title: "画像からキャラクターの設定画を作る", desc: "気に入った画像を持ってくる → LoRA を学習 → 23 パネルの設定画。各段で止まって直せる。", steps: sheetSteps },
  { id: "restyle", title: "キャラクターに別の画風を着せる", desc: "別の画像から学習した画風 LoRA を、キャラの LoRA に重ねる。", steps: restyleSteps },
  { id: "draw", title: "キャラクターの新しい絵を描く", desc: "設定画のあるキャラを、言葉で指示して何枚でも。", steps: drawSteps },
  { id: "style", title: "画風を保存する", desc: "好きな画像の描き方を画風 LoRA にして、名前で呼び出せるようにする。", steps: styleSteps },
  { id: "styleonly", title: "画風だけで全く新しい絵を描く", desc: "保存した画風で、キャラに関係ない絵を描く。", steps: styleOnlySteps },
];

export function home(root) {
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, "何をしたい？"), element("p", {}, "やりたいことを選ぶと、順番に進む画面になります。途中で止まって直せます。")),
    element("div", { class: "cards" }, ...FLOWS.map((flow) => element("a", { class: "card flow", href: `#/flow/${flow.id}` }, element("h2", {}, flow.title), element("p", { class: "muted" }, flow.desc)))));
}

export function flow(root, id) {
  const spec = FLOWS.find((f) => f.id === id);
  if (!spec) return home(root);
  const ctx = state.flow;
  const steps = spec.steps();
  let index = Math.min(ctx.step?.[id] || 0, steps.length - 1);
  const body = element("div", { class: "stack" });
  const crumbs = element("ol", { class: "crumbs" });
  const render = () => {
    ctx.step = { ...(ctx.step || {}), [id]: index }; state.saveFlow();
    crumbs.replaceChildren(...steps.map((s, i) => element("li", { class: i === index ? "active" : i < index ? "done" : "", onclick: () => { if (i <= index) { index = i; render(); } } }, `${i + 1}. ${s.title}`)));
    const nav = element("div", { class: "actions" },
      index > 0 ? element("button", { class: "quiet", onclick: () => { index -= 1; render(); } }, "← 戻る") : "",
      index < steps.length - 1 ? element("button", { onclick: () => { const why = steps[index].ready?.(ctx); if (why) return notice(why, true); index += 1; render(); } }, "次へ →") : element("a", { href: "#/", class: "button-link" }, "ホームへ"));
    const content = element("div", { class: "stack" });
    steps[index].render(content, ctx, () => { const why = steps[index].ready?.(ctx); if (why) return notice(why, true); index += 1; render(); });
    body.replaceChildren(card(steps[index].title, content), nav);
  };
  root.replaceChildren(element("header", { class: "page-head" }, element("h1", {}, spec.title), element("p", {}, spec.desc)), crumbs, body);
  render();
}

// ---------- shared pieces ----------
function picker(placeholder, multiple = true) {
  const text = element("input", { placeholder });
  const file = element("input", { type: "file", accept: "image/*", ...(multiple ? { multiple: "multiple" } : {}), onchange: async () => {
    try { const stored = await API.upload(file.files); const paths = stored.map((item) => item.path); text.value = multiple && text.value ? `${text.value},${paths.join(",")}` : paths.join(","); notice(`${paths.length} 枚を取り込みました`); }
    catch (error) { notice(`取り込めません: ${error.message}`, true); }
  } });
  return { node: element("div", { class: "stack" }, file, text), get value() { return text.value; }, clear() { text.value = ""; file.value = ""; } };
}
function preview(path) { return path ? element("img", { src: API.file(path), alt: path, class: "preview" }) : ""; }
function busy(target, text) { target.replaceChildren(element("p", { class: "muted" }, text)); }

async function chooser(kind, ctx, onPick) {
  // pick an existing character / style, or make a new one
  const items = kind === "character" ? await API.characters() : await API.styles();
  const select = element("select", {}, element("option", { value: "" }, kind === "character" ? "（キャラクターを選ぶ）" : "（画風を選ぶ）"),
    ...items.map((item) => element("option", { value: item.name, selected: (kind === "character" ? ctx.character : ctx.style) === item.name ? "selected" : null },
      `${item.name}（${item.samples.length} 枚・${item.lora_name ? "LoRA あり" : "未学習"}${kind === "character" && item.bible ? "・設定画あり" : ""}）`)));
  select.addEventListener("change", () => onPick(select.value));
  return select;
}

function samplesList(kind, name, target) {
  const load = kind === "character" ? API.character : API.style;
  return load(name).then((rec) => {
    const rows = rec.samples.map((s) => {
      const cap = element("input", { value: s.caption || "", placeholder: "この絵に何が写っているか（衣装・構図など）" });
      return element("div", { class: "actions sample" }, element("img", { src: API.file(s.path), class: "thumb" }), element("span", { class: "muted" }, `#${s.index}`), cap,
        element("button", { class: "quiet", onclick: async () => { await (kind === "character" ? API.setCaption(name, s.index, cap.value) : Promise.resolve()); notice("説明を保存"); } }, "保存"),
        kind === "character" ? element("button", { class: "quiet", onclick: async () => { await API.removeSample(name, s.index); samplesList(kind, name, target); } }, "外す") : "");
    });
    target.replaceChildren(element("p", { class: "muted" }, `${rec.samples.length} 枚 · LoRA: ${rec.lora_name || "未学習"}`), ...rows, rec.samples_sheet ? preview(rec.samples_sheet) : "");
    return rec;
  }).catch((error) => { target.replaceChildren(element("p", { class: "muted" }, error.message)); });
}

async function trainWithProgress(kind, name, steps, target) {
  // the POST blocks until training ends; meanwhile poll the job list for progress
  busy(target, "学習を開始…（約 15 分。ここに進捗が出ます）");
  const timer = setInterval(async () => {
    try {
      const jobs = await API.jobs();
      const job = jobs.find((j) => j.kind === "lora_train" && j.name === name && j.status === "running");
      if (job) target.replaceChildren(element("p", { class: "muted" }, `学習中 ${job.progress.step}/${job.progress.total} step`));
    } catch {}
  }, 5000);
  try {
    const job = await (kind === "character" ? API.train(name, steps) : API.trainStyle(name, steps));
    target.replaceChildren(element("p", {}, `学習完了: ${job.lora_name}`));
    return job;
  } finally { clearInterval(timer); }
}

function previewBlock(ctx, target, opts = {}) {
  const tags = element("input", { value: opts.tags || "full body, standing, front view, looking at viewer", placeholder: "内容の言葉" });
  const seed = element("input", { type: "number", value: "1", min: "0" });
  const out = element("div", { class: "row" });
  const go = element("button", { onclick: async () => { try { busy(out, "数秒…"); const job = await API.previewCharacter(ctx.character, tags.value, seed.value, 2, opts.style ? ctx.style : ""); out.replaceChildren(...job.pictures.map((p) => preview(p.path))); } catch (error) { notice(error.message, true); } } }, "プレビュー 2 枚");
  target.append(element("label", {}, "内容の言葉（絵柄は LoRA が持つので書かない）", tags), element("label", {}, "Seed", seed), go, out);
}

function redrawBlock(ctx, target) {
  const panel = element("select", {});
  const tags = element("textarea", { rows: "2", placeholder: "内容の言葉（空ならそのパネルの既定）" });
  const avoid = element("input", { placeholder: "避ける言葉（例: frills, boots）" });
  const seed = element("input", { type: "number", value: "1", min: "0" });
  const out = element("div", { class: "stack" });
  API.panels().then((items) => { panel.replaceChildren(...items.map((item) => element("option", { value: item.key, "data-tags": item.tags }, `${item.section} / ${item.label}`))); tags.placeholder = panel.selectedOptions[0]?.dataset.tags || ""; });
  panel.addEventListener("change", () => { tags.placeholder = panel.selectedOptions[0]?.dataset.tags || ""; });
  const go = element("button", { onclick: async () => { try { busy(out, "描き直し中…"); const job = await API.redraw(ctx.character, panel.value, tags.value, seed.value, avoid.value); out.replaceChildren(preview(job.path), element("p", { class: "muted" }, `${job.elapsed_s}s · シートも更新: ${job.sheet_path}`), preview(job.sheet_path)); } catch (error) { notice(error.message, true); } } }, "このパネルを描き直す");
  target.append(element("h3", {}, "気になるパネルを言葉で直す（直した内容は次の設定画にも残る）"), element("label", {}, "パネル", panel), element("label", {}, "言葉", tags), element("label", {}, "避ける言葉", avoid), element("label", {}, "Seed", seed), go, out);
}

// ---------- flow 1: pictures → sheet ----------
function sheetSteps() {
  return [
    { title: "キャラクター", ready: (ctx) => ctx.character ? "" : "キャラクターを選ぶか作ってください",
      render: async (target, ctx) => {
        const info = element("div", { class: "muted" });
        target.append(element("p", { class: "muted" }, "既にあるキャラクターを選ぶか、新しく作ります。"), await chooser("character", ctx, (v) => { ctx.character = v; state.saveFlow(); info.textContent = v ? `選択: ${v}` : ""; }), info);
        const name = element("input", { placeholder: "名前（例: Bell）" });
        const desc = element("input", { placeholder: "説明（代名詞を含める。例: she/her, silver twin-tail idol, white and gold outfit）" });
        const attr = element("input", { placeholder: "属性メモ（任意。シートの見出し）" });
        const create = element("button", { onclick: async () => { try { await API.createCharacter(name.value, desc.value, attr.value); ctx.character = name.value; state.saveFlow(); info.textContent = `作成: ${name.value}`; notice("作成しました。次へ"); } catch (error) { notice(error.message, true); } } }, "新しく作る");
        target.append(element("h3", {}, "新しく作る"), element("label", {}, "名前", name), element("label", {}, "説明", desc), element("label", {}, "属性", attr), create);
      } },
    { title: "サンプル画像を集めて直す", ready: (ctx) => "",
      render: (target, ctx) => {
        const list = element("div", { class: "stack" });
        const pick = picker("画像を選ぶ（複数可）");
        const captions = element("input", { placeholder: "画像ごとの説明を | 区切りで（任意。衣装が違う画像を分けて覚えさせる）" });
        const add = element("button", { onclick: async () => { try { await API.addSamples(ctx.character, pick.value, captions.value); pick.clear(); captions.value = ""; samplesList("character", ctx.character, list); } catch (error) { notice(error.message, true); } } }, "追加");
        target.append(element("p", { class: "muted" }, "並べて見て、要らない絵は外し、説明を書き分けます。4 枚以上あると安定します。"), list, pick.node, element("label", {}, "画像ごとの説明", captions), add);
        samplesList("character", ctx.character, list);
      } },
    { title: "LoRA を学習する", ready: (ctx) => "",
      render: async (target, ctx) => {
        const rec = await API.character(ctx.character).catch(() => null);
        const steps = element("input", { type: "number", value: "1200", min: "1" });
        const out = element("div", { class: "stack" });
        target.append(element("p", { class: "muted" }, rec?.lora_name ? `学習済み: ${rec.lora_name}。サンプルや説明を変えたなら学習し直す。変えていないなら次へ。` : "まだ LoRA がありません。学習します（約 15 分）。"),
          element("label", {}, "step 数", steps), element("button", { onclick: () => trainWithProgress("character", ctx.character, steps.value, out).catch((e) => notice(e.message, true)) }, rec?.lora_name ? "学習し直す" : "学習する"), out);
      } },
    { title: "プレビューで確かめる", ready: (ctx) => "",
      render: (target, ctx) => { target.append(element("p", { class: "muted" }, "本人になっているか、衣装は合っているか。ダメなら戻ってサンプルと説明を直し、学習し直す。")); previewBlock(ctx, target); } },
    { title: "設定画を作る・直す", ready: () => "",
      render: async (target, ctx) => {
        const rec = await API.character(ctx.character).catch(() => null);
        const seed = element("input", { type: "number", value: "1", min: "0" });
        const out = element("div", { class: "stack" });
        if (rec?.bible?.sheet_path) out.append(element("p", { class: "muted" }, "前回の設定画"), preview(rec.bible.sheet_path));
        const make = element("button", { onclick: async () => { try { busy(out, "23 パネル生成（約 3 分）…"); const job = await API.bible(ctx.character, seed.value); out.replaceChildren(preview(job.sheet_path), element("p", { class: "muted" }, `${job.sheet_path} / ${job.html_path}`)); } catch (error) { notice(error.message, true); } } }, rec?.bible ? "設定画を作り直す" : "設定画を作る");
        target.append(element("label", {}, "Seed", seed), make, out);
        if (rec?.bible) redrawBlock(ctx, target);
      } },
  ];
}

// ---------- flow 2: character + style ----------
function restyleSteps() {
  return [
    { title: "キャラクター", ready: (ctx) => ctx.character ? "" : "キャラクターを選んでください",
      render: async (target, ctx) => { target.append(element("p", { class: "muted" }, "LoRA 学習済みのキャラクターを選びます（無ければ「画像から設定画を作る」で作る）。"), await chooser("character", ctx, (v) => { ctx.character = v; state.saveFlow(); })); } },
    { title: "画風", ready: (ctx) => ctx.style ? "" : "画風を選んでください",
      render: async (target, ctx) => { target.append(element("p", { class: "muted" }, "学習済みの画風を選びます（無ければ「画風を保存する」で作る）。"), await chooser("style", ctx, (v) => { ctx.style = v; state.saveFlow(); })); } },
    { title: "重ねて確かめる", ready: () => "",
      render: (target, ctx) => {
        const strength = element("input", { type: "number", value: "0.7", min: "0", max: "1.5", step: "0.1" });
        const keep = element("button", { class: "quiet", onclick: async () => { try { await API.setCharacterStyle(ctx.character, ctx.style, strength.value); notice(`${ctx.character} に画風 ${ctx.style} を設定`); } catch (error) { notice(error.message, true); } } }, "この画風をキャラに固定する");
        target.append(element("p", { class: "muted" }, `${ctx.character} × ${ctx.style}。プレビューで見て、良ければキャラに固定すると設定画や新しい絵にも効きます。`), element("label", {}, "画風の強さ", strength));
        previewBlock(ctx, target, { style: true });
        target.append(keep);
      } },
    { title: "設定画に反映する（任意）", ready: () => "",
      render: (target, ctx) => {
        const out = element("div", { class: "stack" });
        target.append(element("p", { class: "muted" }, "画風を重ねた設定画を作り直します（約 3 分）。"), element("button", { onclick: async () => { try { busy(out, "23 パネル生成…"); const job = await API.bible(ctx.character, 1, ctx.style); out.replaceChildren(preview(job.sheet_path)); } catch (error) { notice(error.message, true); } } }, "画風付きで設定画を作る"), out);
      } },
  ];
}

// ---------- flow 3: new pictures of a character ----------
function drawSteps() {
  return [
    { title: "キャラクター", ready: (ctx) => ctx.character ? "" : "キャラクターを選んでください",
      render: async (target, ctx) => { target.append(await chooser("character", ctx, (v) => { ctx.character = v; state.saveFlow(); })); } },
    { title: "描く", ready: () => "",
      render: async (target, ctx) => {
        const prompt = element("textarea", { rows: "2", placeholder: "内容（例: waving on a concert stage, spotlight, full body）" });
        const style = await chooser("style", ctx, (v) => { ctx.style = v; state.saveFlow(); });
        const seed = element("input", { type: "number", value: "1", min: "0" });
        const out = element("div", { class: "stack" });
        const go = element("button", { onclick: async () => { try { busy(out, "生成中…"); const job = await API.fromBible(ctx.character, prompt.value, seed.value, style.value); out.prepend(preview(job.path), element("p", { class: "muted" }, `${job.prompt || prompt.value} · seed ${seed.value} · ${job.elapsed_s}s`)); } catch (error) { notice(error.message, true); } } }, "描く");
        target.append(element("label", {}, "内容の言葉", prompt), element("label", {}, "画風（任意）", style), element("label", {}, "Seed", seed), go, out);
      } },
  ];
}

// ---------- flow 4: save a style ----------
function styleSteps() {
  return [
    { title: "画風", ready: (ctx) => ctx.style ? "" : "画風を選ぶか作ってください",
      render: async (target, ctx) => {
        const info = element("div", { class: "muted" });
        target.append(await chooser("style", ctx, (v) => { ctx.style = v; state.saveFlow(); }), info);
        const name = element("input", { placeholder: "画風名（例: glow）" }); const note = element("input", { placeholder: "メモ（任意）" });
        target.append(element("h3", {}, "新しく作る"), element("label", {}, "名前", name), element("label", {}, "メモ", note),
          element("button", { onclick: async () => { try { await API.createStyle(name.value, note.value); ctx.style = name.value; state.saveFlow(); info.textContent = `作成: ${name.value}`; notice("作成しました。次へ"); } catch (error) { notice(error.message, true); } } }, "新しく作る"));
      } },
    { title: "画像を集める", ready: () => "",
      render: (target, ctx) => {
        const list = element("div", { class: "stack" });
        const pick = picker("画風の画像（複数可。被写体がばらけていると画風だけが学習される）");
        const captions = element("input", { placeholder: "画像ごとの説明を | 区切りで（何が写っているか。任意）" });
        target.append(element("p", { class: "muted" }, "同じキャラばかりだと画風にそのキャラが混ざります。キャラシートや色見本の入った画像は避けてください。"), list, pick.node, element("label", {}, "説明", captions),
          element("button", { onclick: async () => { try { await API.addStyleSamples(ctx.style, pick.value, captions.value); pick.clear(); samplesList("style", ctx.style, list); } catch (error) { notice(error.message, true); } } }, "追加"));
        samplesList("style", ctx.style, list);
      } },
    { title: "画風 LoRA を学習する", ready: () => "",
      render: async (target, ctx) => {
        const rec = await API.style(ctx.style).catch(() => null);
        const steps = element("input", { type: "number", value: "1200", min: "1" }); const out = element("div", { class: "stack" });
        target.append(element("p", { class: "muted" }, rec?.lora_name ? `学習済み: ${rec.lora_name}` : "約 15 分。"), element("label", {}, "step 数", steps),
          element("button", { onclick: () => trainWithProgress("style", ctx.style, steps.value, out).catch((e) => notice(e.message, true)) }, rec?.lora_name ? "学習し直す" : "学習する"), out);
      } },
    { title: "試し描き", ready: () => "",
      render: (target, ctx) => {
        const prompt = element("textarea", { rows: "2", value: "a small red fox sitting on a snowy street at night under a streetlamp, no humans" });
        const out = element("div", { class: "stack" });
        target.append(element("p", { class: "muted" }, "画風だけで 1 枚描いて、狙った描き方になっているか見ます。"), element("label", {}, "内容", prompt),
          element("button", { onclick: async () => { try { busy(out, "生成中…"); const job = await API.image(prompt.value, ctx.style); out.replaceChildren(preview(job.path)); } catch (error) { notice(error.message, true); } } }, "描く"), out);
      } },
  ];
}

// ---------- flow 5: style only ----------
function styleOnlySteps() {
  return [
    { title: "画風", ready: (ctx) => ctx.style ? "" : "画風を選んでください",
      render: async (target, ctx) => { target.append(await chooser("style", ctx, (v) => { ctx.style = v; state.saveFlow(); })); } },
    { title: "描く", ready: () => "",
      render: (target, ctx) => {
        const prompt = element("textarea", { rows: "2", placeholder: "内容（例: 1boy, knight in dark armor on a cliff, wind, cape）" });
        const seed = element("input", { type: "number", value: "1", min: "0" }); const out = element("div", { class: "stack" });
        target.append(element("label", {}, "内容の言葉", prompt), element("label", {}, "Seed", seed),
          element("button", { onclick: async () => { try { busy(out, "生成中…"); const job = await API.image(prompt.value, ctx.style, seed.value); out.prepend(preview(job.path), element("p", { class: "muted" }, `${job.prompt} · ${job.elapsed_s}s`)); } catch (error) { notice(error.message, true); } } }, "描く"), out);
      } },
  ];
}
