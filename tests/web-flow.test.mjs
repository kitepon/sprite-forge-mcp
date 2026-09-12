import test from 'node:test';
import assert from 'node:assert/strict';
import { Node as FakeNode, installDom, all } from './web-dom.mjs';
installDom();
const { API } = await import('../web/api.js');
const { samples, flow } = await import('../web/flows.js');
const { state } = await import('../web/state.js');
const { pendingFiles, saveDraft } = await import('../web/drafts.js');
const { referenceNotes, saveCaption } = await import('../web/intent.js');
const { learning } = await import('../web/learning.js');
const { refreshJobs } = await import('../web/jobs.js');

test('古い確認待ちは希望を引き継ぎ、再開始の応答待ちに過去の状態を表示しない', async () => {
  const rec = {key:'legacy',created:'now',samples:[],lora_name:''};
  const job = {job_id:'old',stage:'training',references:[],record_kind:'character',record_key:'legacy',record_created:'now',kind:'intent',status:'awaiting_confirmation',learning_steps:1200,proposal:{changes:[],observations:[],questions:['保存済みの確認事項']}};
  API.character = async () => rec;
  API.commentIntents = async () => [{stage:'samples',original_comment:'保存済みの画風への希望'}];
  API.jobs = async () => [job];
  let release;
  API.startLearning = () => new Promise(resolve => {release=resolve;});
  const root=new FakeNode('root'), cleanup=[];
  await learning(root,'character','旧記録の確認',cleanup,()=>{});
  assert.ok(all(root).some(n=>n.children.includes('保存した画像と希望を引き継ぎます。「この内容で学習を始める」を押すと、読み取りから学習まで続けて進みます。')));
  assert.ok(all(root).some(n=>n.value === '保存済みの画風への希望'));
  assert.ok(!all(root).some(n=>n.children.includes('読み取った希望の確認')));
  assert.ok(all(root).some(n=>n.children.includes('AIが読み取った内容')));
  assert.ok(all(root).some(n=>n.children.includes('保存済みの確認事項')));
  const start=all(root).find(n=>n.textContent === 'この内容で学習を始める');
  const pending=start.events.click(); await new Promise(resolve=>setImmediate(resolve));
  assert.ok(all(root).some(n=>n.children.includes('学習の開始を確認しています')));
  assert.ok(!all(root).some(n=>n.children.includes('解釈案の確認待ち')));
  assert.ok(all(root).some(n=>n.children.includes('保存済みの確認事項')));
  release(job); await pending;
  job.status='confirmed'; job.training_job_id='completed';
  API.jobs=async()=>[job,{job_id:'completed',kind:'lora_train',status:'completed',record_kind:'character',record_key:'legacy',record_created:'now'}];
  await refreshJobs();
  assert.ok(all(root).some(n=>n.children.includes('AIが読み取った内容')));
  const repeat=start.events.click(); await new Promise(resolve=>setImmediate(resolve));
  assert.ok(all(root).some(n=>n.children.includes('学習の開始を確認しています')));
  assert.ok(!all(root).some(n=>n.children.includes('できました')));
  release(job); await repeat; cleanup.forEach(fn=>fn());
});

test('質問のない採用案は承認操作にせず、学習中・完了後も説明を残す', async () => {
  const rec = {key:'one-action',created:'now',samples:[],lora_name:''};
  const proposal = {training_samples:[],observations:[],questions:[],changes:[{feature:'outfit',scope:'persistent',reason_ja:'衣装を素材から採用'}]};
  const job = {job_id:'reading',stage:'training',references:[],record_kind:'character',record_key:rec.key,record_created:'now',kind:'intent',status:'awaiting_confirmation',learning_steps:3,proposal,interpreter:{model:'試験用',elapsed_seconds:1}};
  API.character = async () => rec; API.commentIntents = async () => []; API.jobs = async () => [job];
  const root = new FakeNode('root'), cleanup=[];
  let ready = false;
  await learning(root,'character','一回で開始',cleanup,value=>{ready=value;});
  assert.ok(all(root).some(n=>n.children.includes('読み取った希望の確認')));
  assert.ok(all(root).some(n=>n.children.includes('衣装を素材から採用')));
  const start=all(root).find(n=>n.textContent === 'この内容で学習を始める');
  const proposalBox = all(root).find(n=>n.className === 'intent-proposal stack');
  assert.ok(all(proposalBox.children.at(-2)).includes(start));
  assert.ok(proposalBox.lastChild.children.some(n=>n.children?.includes('処理の記録')));
  assert.ok(!all(root).some(n=>n.children.includes('「この内容で学習を始める」を押してください。')));
  assert.equal(ready,false);
  let calls=0, release;
  API.startLearning=()=>{ calls++; job.status='running'; return new Promise(resolve=>{release=resolve;}); };
  const pending=start.events.click(); await new Promise(resolve=>setImmediate(resolve));
  await refreshJobs();
  assert.equal(calls,1); assert.equal(start.disabled,true);
  assert.ok(all(root).some(n=>n.children.includes('読み取りが終わると、教材を準備して学習へ進みます。回答が必要な質問がある場合だけお知らせします。')));
  job.status='confirmed'; job.accepted=proposal; job.training_job_id='train';
  const child={job_id:'train',kind:'lora_train',status:'running',progress:{step:1,total:3}};
  API.jobs=async()=>[child,job]; await refreshJobs();
  assert.ok(all(root).some(n=>n.children.includes('衣装を素材から採用')));
  assert.ok(all(root).some(n=>n.tag === 'progress'));
  child.status='completed'; release(job); await pending;
  assert.equal(ready,true);
  assert.ok(all(root).some(n=>n.tag === 'details' && n.children.some(c=>c.children?.includes('学習をやり直す')) && all(n).includes(start)));
  assert.ok(all(root).some(n=>n.children.includes('衣装を素材から採用')));
  cleanup.forEach(fn=>fn());
});

test('失敗した学習のあとは、やり直すを開かなくても開始ボタンがある', async () => {
  const rec = {key:'retry',created:'now',samples:[{path:'a.png'}],lora_name:'old.safetensors'};
  const job = {job_id:'dead',stage:'training',references:[],record_kind:'character',record_key:rec.key,record_created:'now',kind:'intent',status:'failed',learning_steps:1200,error:'中断'};
  API.character = async () => rec; API.commentIntents = async () => []; API.jobs = async () => [job];
  const root = new FakeNode('root'), cleanup=[];
  await learning(root,'character','失敗後',cleanup,()=>{});
  const start = all(root).find(n => n.textContent === '参考画像から LoRA を作り直す');
  assert.ok(start);
  const redo = all(root).find(n => n.tag === 'details' && n.children.some(c => c.children?.includes('学習をやり直す')));
  assert.ok(redo.hidden);
  cleanup.forEach(fn=>fn());
});

for (const kind of ['character', 'style']) test(`${kind}：画像選択だけで追加し、完了まで次へ進めない`, async t => {
  t.mock.method(URL, 'createObjectURL', () => 'blob:test');
  t.mock.method(URL, 'revokeObjectURL', () => {});
  let record = { samples: [] }, uploaded = 0, ready = false;
  API[kind] = async () => structuredClone(record);
  API.commentIntents = async () => [];
  API.upload = async () => [{ path: `upload-${++uploaded}` }];
  const commits = [];
  API[kind === 'character' ? 'addSamples' : 'addStyleSamples'] = (_name, path) => new Promise(resolve => commits.push(() => {
    record.samples.push({ index: record.samples.length, path, caption: '' }); resolve(structuredClone(record));
  }));
  const root = new FakeNode('root'), cleanup = [];
  const save = await samples(root, kind, kind, cleanup, () => {}, value => { ready = value; });
  const file = all(root).find(n => n.attrs.type === 'file'); file.files = [{ name: 'a' }, { name: 'b' }];
  file.events.change(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(ready, false); assert.equal(uploaded, 1);
  commits.shift()(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(ready, false); assert.equal(uploaded, 2);
  commits.shift()(); await pendingFiles.get(`${kind}:${kind}`).promise;
  assert.equal(ready, true); assert.equal(record.samples.length, 2);
  assert.ok(!all(root).some(n => n.children.includes('選んだ画像を追加')));
  await save(); cleanup.forEach(fn => fn());
});

test('追加途中の失敗は成功分を保ち、再送は未追加分だけを処理する', async t => {
  t.mock.method(URL, 'createObjectURL', () => 'blob:test'); t.mock.method(URL, 'revokeObjectURL', () => {});
  t.mock.method(globalThis, 'setTimeout', () => 0);
  let record = { samples: [] }, uploads = 0, fail = true;
  API.character = async () => structuredClone(record); API.commentIntents = async () => [];
  API.upload = async () => [{ path: `p-${++uploads}` }];
  API.addSamples = async (_, path) => {
    if (path === 'p-2' && fail) throw new Error('保存できません');
    record.samples.push({ index: record.samples.length, path, caption: '' }); return structuredClone(record);
  };
  const root = new FakeNode('root'), cleanup = []; let ready;
  await samples(root, 'character', '再送', cleanup, () => {}, r => { ready = r; });
  const input = all(root).find(n => n.attrs.type === 'file'); input.files = [{ name: 'a' }, { name: 'b' }]; input.events.change();
  const pending = pendingFiles.get('character:再送'); await pending.promise;
  assert.equal(ready, false); assert.equal(record.samples.length, 1); assert.equal(pending.length, 1);
  fail = false;
  all(root).find(n => n.children.includes('追加できなかった画像を再送する')).events.click(); await pending.promise;
  assert.equal(uploads, 2); assert.equal(record.samples.length, 2); assert.equal(ready, true);
  cleanup.forEach(fn => fn());
});

test('希望の自動保存と移動時の保存が重なっても、古い入力を後から書かない', async () => {
  API.commentIntents = async () => [];
  const calls = []; let release;
  API.saveComment = async body => { calls.push(body.comment); if (calls.length === 1) await new Promise(resolve => { release = resolve; }); return body; };
  const notes = await referenceNotes(new FakeNode('root'), { name: '保存順', kind: 'character' });
  notes.input.value = '古い希望'; const first = notes.save(); await new Promise(resolve => setImmediate(resolve));
  notes.input.value = '新しい希望'; const second = notes.save();
  assert.deepEqual(calls, ['古い希望']); release(); await Promise.all([first, second]);
  assert.deepEqual(calls, ['古い希望', '新しい希望']);
});

test('キャラクターを選ぶ前の第1工程が、台帳の未取得で壊れない', async () => {
  state.flow = {};
  API.characters = async () => [];
  API.jobs = async () => [];
  const root = new FakeNode('root');
  const dispose = flow(root, 'sheet');
  for (let tick = 0; tick < 6; tick++) await new Promise(resolve => setTimeout(resolve, 0));
  const nodes = all(root);
  assert.ok(!nodes.some(n => n.children.includes('読み込めませんでした')));
  assert.ok(nodes.some(n => n.children.includes('キャラクター')));
  assert.ok(nodes.some(n => n.textContent === '選ぶか、新しく登録してください。'));
  assert.equal(nodes.find(n => n.className === 'next-step').children[1].disabled, true);
  dispose();
});

test('画像コメントの自動保存も順序を保つ', async () => {
  const calls = []; let release;
  API.setCaption = async (_name, _index, value) => { calls.push(value); if (calls.length === 1) await new Promise(resolve => { release = resolve; }); };
  const sample = { index: 0, path: 'image', caption: '' };
  saveDraft('character:保存順:caption:0:image', '古い希望');
  const first = saveCaption('character', '保存順', sample, '古い希望'); await new Promise(resolve => setImmediate(resolve));
  saveDraft('character:保存順:caption:0:image', '新しい希望');
  const second = saveCaption('character', '保存順', sample, '新しい希望'); release(); await Promise.all([first, second]);
  assert.deepEqual(calls, ['古い希望', '新しい希望']);
});
