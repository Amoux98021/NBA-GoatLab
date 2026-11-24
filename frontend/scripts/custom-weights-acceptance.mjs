// STEP-0041: mounted custom weights acceptance, using the local CDP pipe pattern from STEP-0037.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
const baseUrl = process.env.GOATLAB_CUSTOM_ACCEPTANCE_URL ?? "http://127.0.0.1:3041";
const origin = new URL(baseUrl);
assert.ok(origin.protocol === "http:" && ["localhost", "127.0.0.1"].includes(origin.hostname) && origin.origin === baseUrl && !origin.username && !origin.password, "Exact loopback origin required");
const commandTimeoutMs = 10000;
const chromePath = process.env.GOATLAB_CHROME_BIN ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
class ChromePipe {
  constructor(executable, userDataDir) {
    this.nextId = 0;
    this.pending = new Map();
    this.events = new Set();
    this.buffer = Buffer.alloc(0);
    this.stderr = "";
    this.spawnError = null;
    this.process = spawn(executable, [
      "--headless=new",
      "--remote-debugging-pipe",
      `--user-data-dir=${userDataDir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-domain-reliability",
      "--disable-sync",
      "--metrics-recording-only",
      "--no-pings",
      "--disable-features=OptimizationHints,MediaRouter",
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
      "about:blank",
    ], {
      env: { PATH: process.env.PATH ?? "/usr/bin:/bin", TMPDIR: tmpdir() },
      stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"],
    });
    this.input = this.process.stdio[3];
    this.output = this.process.stdio[4];
    this.output.on("data", (chunk) => this.onData(chunk));
    this.process.stderr.on("data", (chunk) => { this.stderr += chunk.toString(); });
    this.process.on("error", (error) => {
      this.spawnError = error;
      this.rejectPending(error);
    });
    this.process.on("exit", (code) => {
      if (this.pending.size > 0) this.rejectPending(new Error(`Chrome exited with ${code}: ${this.stderr.slice(-1000)}`));
    });
  }

  rejectPending(error) {
    for (const { reject, timer } of this.pending.values()) {
      clearTimeout(timer);
      reject(error);
    }
    this.pending.clear();
  }

  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    let boundary = this.buffer.indexOf(0);
    while (boundary !== -1) {
      const payload = this.buffer.subarray(0, boundary).toString();
      this.buffer = this.buffer.subarray(boundary + 1);
      if (payload) this.onMessage(JSON.parse(payload));
      boundary = this.buffer.indexOf(0);
    }
  }

  onMessage(message) {
    if (message.id !== undefined) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(new Error(`${pending.method}: ${message.error.message}`));
      else pending.resolve(message.result ?? {});
      return;
    }
    for (const listener of this.events) listener(message);
  }

  send(method, params = {}, sessionId) {
    if (this.spawnError) return Promise.reject(this.spawnError);
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} exceeded ${commandTimeoutMs}ms`));
      }, commandTimeoutMs);
      this.pending.set(id, { method, resolve, reject, timer });
      const message = { id, method, params };
      if (sessionId) message.sessionId = sessionId;
      this.input.write(`${JSON.stringify(message)}\0`, (error) => {
        if (!error) return;
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      });
    });
  }

  onEvent(listener) {
    this.events.add(listener);
    return () => this.events.delete(listener);
  }

  async close() {
    const exited = () => this.process.exitCode !== null || this.process.signalCode !== null;
    const waitForExit = (milliseconds) => {
      if (exited()) return Promise.resolve(true);
      return new Promise((resolve) => {
        const finish = () => { clearTimeout(timer); resolve(true); };
        const timer = setTimeout(() => { this.process.off("exit", finish); resolve(false); }, milliseconds);
        this.process.once("exit", finish);
      });
    };
    if (!exited()) await Promise.race([this.send("Browser.close").catch(() => {}), delay(1000)]);
    if (!(await waitForExit(1500))) {
      this.process.kill("SIGTERM");
      if (!(await waitForExit(1500))) {
        this.process.kill("SIGKILL");
        await waitForExit(1000);
      }
    }
    this.input.destroy();
    this.output.destroy();
    this.process.stderr.destroy();
    this.process.unref();
  }
}

async function evaluate(chrome, sessionId, expression) {
  const result = await chrome.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  }, sessionId);
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text ?? "browser evaluation failed");
  return result.result.value;
}

async function waitForReady(chrome, sessionId) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    const state = await evaluate(chrome, sessionId, "document.readyState").catch(() => "loading");
    if (state === "complete") {
      await delay(350);
      return;
    }
    await delay(100);
  }
  throw new Error("page did not reach readyState=complete");
}

async function navigate(chrome, sessionId, url) {
  const result = await chrome.send("Page.navigate", { url }, sessionId);
  if (result.errorText) throw new Error(`navigation failed: ${result.errorText}`);
  await waitForReady(chrome, sessionId);
}


const a = "player_3a6d2e4aeafb5b0c9dba522e3c245db0";
const b = "player_b99799c86e9f5cc1a5008c2c8c721213";
const basePath = `/compare/${a}/${b}`;
const userDataDir = await mkdtemp(path.join(tmpdir(), "goatlab-custom-chrome-"));
const evidence = await mkdtemp(path.join(tmpdir(), "goatlab-step0041-evidence-"));
const chrome = new ChromePipe(chromePath, userDataDir);
const blocked = [], exceptions = [], requests = [];
let detach = () => {};
const timer = setTimeout(() => { void chrome.close(); }, 120000);
try {
  await chrome.send("Browser.getVersion");
  const {browserContextId} = await chrome.send("Target.createBrowserContext");
  const {targetId} = await chrome.send("Target.createTarget", {url:"about:blank",browserContextId});
  const {sessionId} = await chrome.send("Target.attachToTarget", {targetId,flatten:true});
  await chrome.send("Page.enable",{},sessionId);
  await chrome.send("Runtime.enable",{},sessionId);
  await chrome.send("Network.enable",{},sessionId);
  await chrome.send("Fetch.enable",{patterns:[{urlPattern:"*",requestStage:"Request"}]},sessionId);
  detach = chrome.onEvent((event) => {
    if (event.sessionId !== sessionId) return;
    if (event.method === "Runtime.exceptionThrown") exceptions.push(event.params.exceptionDetails.text);
    if (event.method !== "Fetch.requestPaused") return;
    const url = event.params.request.url;
    const allowed = url.startsWith("data:") || new URL(url).origin === baseUrl;
    if (!allowed) blocked.push(url);
    requests.push(url);
    void chrome.send(allowed ? "Fetch.continueRequest" : "Fetch.failRequest", allowed ? {requestId:event.params.requestId} : {requestId:event.params.requestId,errorReason:"BlockedByClient"},sessionId);
  });
  const evalJs = (s) => evaluate(chrome,sessionId,s);
  const key = async (key, code, windowsVirtualKeyCode) => {
    await chrome.send("Input.dispatchKeyEvent",{type:"keyDown",key,code,windowsVirtualKeyCode,...(key==="Enter"?{text:"\r"}:{})},sessionId);
    await chrome.send("Input.dispatchKeyEvent",{type:"keyUp",key,code,windowsVirtualKeyCode},sessionId);
    await delay(50);
  };
  const state = () => evalJs(`({values:[...document.querySelectorAll('.custom-weights input')].map(e=>+e.value),text:document.querySelector('.custom-weights').innerText,url:location.href,prob:[...document.querySelectorAll('.probability-split__labels strong')].map(e=>e.innerText),overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth})`);
  const results = [];
  for (const width of [375,768,1024,1440]) {
    await chrome.send("Emulation.setDeviceMetricsOverride",{width,height:900,deviceScaleFactor:1,mobile:width<800},sessionId);
    await navigate(chrome,sessionId,baseUrl+basePath);
    await evalJs(`window.scrollTo({top:document.querySelector('.custom-weights').getBoundingClientRect().top+scrollY,behavior:'instant'})`);
    const controls = await evalJs(`([...document.querySelectorAll('.custom-weights input')].map(e=>({name:document.querySelector('label[for="'+e.id+'"]').innerText,min:e.min,max:e.max,height:e.getBoundingClientRect().height})))`);
    assert.equal(controls.length,7); assert.ok(controls.every(e=>e.name&&e.min==='0'&&e.max==='100'&&e.height>=44));
    const initial = await state(); assert.equal(initial.overflow,0); assert.match(initial.text,/Default-equivalent/);
    const screenshot = await chrome.send("Page.captureScreenshot",{format:"png"},sessionId);
    await writeFile(path.join(evidence,`${width}-controls.png`),Buffer.from(screenshot.data,"base64"));
    const requestCount = requests.length;
    await evalJs(`document.querySelector('#weight-WINNING').focus()`);
    await key("ArrowRight","ArrowRight",39);
    const raised = await state();
    assert.equal(raised.values[6],12);
    assert.equal(raised.values.reduce((a,b)=>a+b,0),100);
    assert.notDeepEqual(raised.values.slice(0,6),initial.values.slice(0,6));
    await key("ArrowLeft","ArrowLeft",37);
    assert.deepEqual((await state()).values,initial.values,"Same-slider nudges should be reversible");
    await key("Home","Home",36);
    const removed = await state();
    assert.equal(removed.values[6],0);
    assert.equal(removed.values.reduce((a,b)=>a+b,0),100);
    await key("End","End",35);
    const single = await state(); assert.deepEqual(single.values,[0,0,0,0,0,0,100]); assert.match(single.text,/94.84–94.84/); assert.match(single.text,/99.96–99.96/); assert.match(single.text,/Custom win probability unavailable/); assert.deepEqual(single.prob,initial.prob);
    assert.equal(requests.length,requestCount,"Slider changes must not request data");
    const focused = await evalJs(`({id:document.activeElement.id,outline:getComputedStyle(document.activeElement).outlineStyle})`); assert.equal(focused.id,"weight-WINNING"); assert.notEqual(focused.outline,"none");
    const shared = single.url;
    await navigate(chrome,sessionId,shared);
    const restored = await state(); assert.deepEqual(restored.values,single.values); assert.equal(restored.url,shared);
    assert.equal(restored.overflow,0);
    await evalJs(`document.querySelector('#weight-WINNING').focus()`);
    await key("ArrowLeft","ArrowLeft",37);
    assert.deepEqual((await state()).values,[0,0,0,0,1,0,99]);
    await key("End","End",35);
    await evalJs(`window.scrollTo({top:document.querySelector('.custom-result-grid').getBoundingClientRect().top+scrollY,behavior:'instant'})`);
    const screenshot2 = await chrome.send("Page.captureScreenshot",{format:"png"},sessionId);
    await writeFile(path.join(evidence,`${width}-single-winning.png`),Buffer.from(screenshot2.data,"base64"));
    const swapped = await evalJs(`document.querySelector('.custom-weights a[href*="weights="]').href`);
    await navigate(chrome,sessionId,swapped);
    assert.ok(swapped.includes(`/compare/${b}/${a}`)); assert.deepEqual((await state()).values,single.values);
    await evalJs(`document.querySelector('.custom-weights button').click()`);
    assert.deepEqual((await state()).values,[17,14,16,14,18,10,11]);
    await navigate(chrome,sessionId,baseUrl+"/compare");
    await evalJs(`document.querySelector('[role=combobox]').focus()`);
    await chrome.send("Input.insertText",{text:"Barkley"},sessionId);
    let dropdown;
    for (let i=0;i<40&&!dropdown;i++) {
      await delay(100);
      dropdown = await evalJs(`(() => { const input=document.querySelector('[role=combobox]'), list=document.querySelector('[role=listbox]'); if (!list) return null; const a=input.getBoundingClientRect(), b=list.getBoundingClientRect(); return {aligned: Math.abs(a.left-b.left)<2&&Math.abs(a.right-b.right)<2, gap:b.top-a.bottom, overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,text:list.innerText, right:b.right, max:innerWidth}; })()`);
    }
    assert.ok(dropdown?.aligned && dropdown.gap>=0 && dropdown.gap<=9 && dropdown.right<=dropdown.max);
    assert.equal(dropdown.overflow,0);
    assert.match(dropdown.text,/Charles Barkley/);
    await key("Escape","Escape",27);
    assert.equal(await evalJs(`document.querySelector('[role=combobox]').getAttribute('aria-expanded')`),"false");
    await navigate(chrome,sessionId,baseUrl+"/players/"+a);
    for(const index of [0,2,3]) {
      await evalJs(`(() => {const s=document.querySelectorAll('.info-tip summary')[${index}]; s.scrollIntoView({block:'center',behavior:'instant'}); s.focus();})()`);
      await key("Enter","Enter",13);
      await delay(150);
      const tip = await evalJs(`(() => { const s=document.activeElement, n=document.getElementById(s.getAttribute('aria-controls')); if(n?.dataset.placed!=='true') return {active:s.tagName,label:s.getAttribute('aria-label'),open:s.closest('details')?.open,placed:n?.dataset.placed}; const b=n.getBoundingClientRect(); return {inside:b.left>=10&&b.right<=innerWidth-10&&b.top>=10&&b.bottom<=innerHeight-10&&b.height>0,visible:n.contains(document.elementFromPoint(b.left+5,b.top+5)),overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth}; })()`);
      assert.ok(tip?.inside && tip.visible, `Explanation ${index} clipped at ${width}px: ${JSON.stringify(tip)}`);
      assert.equal(tip.overflow,0);
      await key("Escape","Escape",27);
      assert.equal(await evalJs(`!!document.activeElement.closest('details').open`),false);
    }
    results.push({width,keyboardRebalance:true,singleWinning:true,shareRoundTrip:true,swapPreserved:true,reset:true,noSliderRequests:true,noOverflow:true,dropdown:true,infoTips:true});
  }
  await navigate(chrome,sessionId,baseUrl+basePath+'?weights=v1:0,0,100,0,0,0,0');
  assert.match((await state()).text,/98.68–98.68/);
  await navigate(chrome,sessionId,baseUrl+basePath+'?weights=v1:0,0,0,0,0,0,0');
  assert.match((await state()).text,/Positive total required/);
  await navigate(chrome,sessionId,baseUrl+basePath+'?weights=v1:1,2,3,4,5,6,7');
  assert.deepEqual((await state()).values,[4,7,11,14,18,21,25]);
  assert.match((await state()).text,/exact shared proportions/);
  assert.equal(new URL((await state()).url).searchParams.get("weights"),"v1:1,2,3,4,5,6,7");
  await navigate(chrome,sessionId,baseUrl+basePath+'?weights=bad');
  assert.match((await state()).text,/Invalid or unsupported/);
  await navigate(chrome,sessionId,baseUrl+`/compare/${a}/player_00073e3eef455e09bf506949f46b4139`);
  assert.match((await state()).text,/Unavailable:/);
  assert.match((await state()).text,/Default probability unavailable/);
  assert.equal(await evalJs(`document.querySelector('.probability-split')===null`),true);
  await navigate(chrome,sessionId,baseUrl+basePath);
  await evalJs(`history.pushState(history.state,'',location.pathname+'?weights=v1:0,0,100,0,0,0,0'); dispatchEvent(new PopStateEvent('popstate'))`);
  assert.deepEqual((await state()).values,[0,0,100,0,0,0,0]);
  await evalJs(`history.pushState(history.state,'',location.pathname+'?weights=v1:0,0,0,0,0,0,100'); dispatchEvent(new PopStateEvent('popstate'))`);
  assert.deepEqual((await state()).values,[0,0,0,0,0,0,100]);
  await chrome.send("Emulation.setEmulatedMedia",{features:[{name:"prefers-reduced-motion",value:"reduce"}]},sessionId);
  assert.equal(await evalJs(`matchMedia('(prefers-reduced-motion: reduce)').matches`),true);
  assert.deepEqual(blocked,[]); assert.deepEqual(exceptions,[]);
  const report = {step:"STEP-0041",baseUrl,results,extraCases:["100% Offense","all-zero shared URL","invalid URL","unavailable default and evidence","history restoration","reduced motion"],blockedRequests:blocked,runtimeExceptions:exceptions,evidence};
  await writeFile(path.join(evidence,"report.json"),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
} finally {
  clearTimeout(timer); detach(); await chrome.close(); await rm(userDataDir,{recursive:true,force:true});
}
