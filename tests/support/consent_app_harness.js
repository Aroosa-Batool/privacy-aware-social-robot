// Runs bangle/consent_app.js with stand-ins for the Bangle.js globals, feeds it command lines
// produced by the Python side, and prints what the app writes back.
const fs = require("fs");
const vm = require("vm");
const [appPath, stepsPath] = process.argv.slice(2);
const steps = JSON.parse(fs.readFileSync(stepsPath, "utf8"));
const out = [];
const ctx = {
  timers: [], prompt: null,
  echo() {}, NRF: { on() {} },
  Bangle: { setOptions() {}, setLCDPower() {}, setLocked() {}, setLCDBrightness() {}, buzz() { return Promise.resolve(); } },
  g: { reset() {}, clear() {}, setFont() {}, drawString() {}, flip() {} },
  Bluetooth: { println(s) { out.push(String(s)); } },
  setInterval() { return 1; }, clearInterval() {},
};
ctx.setTimeout = (f, ms) => {
  const timer = { f, ms, active: true };
  ctx.timers.push(timer);
  return timer;
};
ctx.clearTimeout = (timer) => { timer.active = false; };
function fire(timer) {
  if (timer && timer.active) {
    timer.active = false;
    timer.f();
  }
}
let visiblePrompt = null;
ctx.E = { showPrompt(msg, opts) {
  const previous = visiblePrompt;
  visiblePrompt = null;
  if (previous && previous.remove) previous.remove();
  if (msg === undefined) return;  // firmware removes the UI without settling the button promise
  if (ctx.throwOnPrompt) throw new Error("display unavailable");
  return new Promise((resolve, reject) => {
    visiblePrompt = ctx.prompt = { msg, title: opts.title, remove: opts.remove, resolve, reject };
  });
} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(appPath, "utf8"), ctx);
const tick = () => new Promise((r) => setImmediate(r));
(async () => {
  const report = [];
  const prompts = {};
  for (const step of steps) {
    out.length = 0; ctx.prompt = null; ctx.timers.length = 0;
    ctx.throwOnPrompt = step.throwOnPrompt;
    if (step.legacy) ctx.consentV2 = undefined;
    const code = Buffer.from(step.bytes, "base64").toString("latin1");
    if (!code.startsWith("\x10") || !code.endsWith("\n")) throw new Error("bad framing");
    vm.runInContext(code.slice(1, -1), ctx);
    if (ctx.prompt) prompts[step.name] = ctx.prompt;
    const expiry = ctx.timers[0];
    if (step.expire) fire(expiry);
    if (step.removeWithoutAnswer) ctx.E.showPrompt();
    if (step.reachExpiryAfterRemoval) fire(expiry);
    if (step.lateFrom) prompts[step.lateFrom].resolve(1);
    if (step.reject) ctx.prompt.reject(new Error("display failed"));
    if (step.press !== undefined) {
      if (!step.removeAfterAnswer) ctx.E.showPrompt();
      ctx.prompt.resolve(step.press);
      if (step.removeAfterAnswer) { await tick(); ctx.E.showPrompt(); }
    }
    if (step.duplicate) ctx.prompt.resolve(1);
    await tick(); await tick();
    for (const timer of ctx.timers) if (timer !== expiry) fire(timer);
    await tick();
    report.push({ name: step.name, replies: [...out], prompt: ctx.prompt && { msg: ctx.prompt.msg, title: ctx.prompt.title },
                  timeoutMs: expiry ? expiry.ms : null });
  }
  console.log(JSON.stringify(report));
})();
