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
  setInterval() { return 1; }, clearInterval() {}, clearTimeout() {},
};
ctx.setTimeout = (f, ms) => { ctx.timers.push({ f, ms }); return ctx.timers.length; };
ctx.E = { showPrompt(msg, opts) {
  if (msg === undefined) return undefined;   // dismiss
  return new Promise((resolve) => { ctx.prompt = { msg, title: opts.title, resolve }; });
} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(appPath, "utf8"), ctx);
const tick = () => new Promise((r) => setImmediate(r));
(async () => {
  const report = [];
  for (const step of steps) {
    out.length = 0; ctx.prompt = null; ctx.timers.length = 0;
    const code = Buffer.from(step.bytes, "base64").toString("latin1");
    if (!code.startsWith("\x10") || !code.endsWith("\n")) throw new Error("bad framing");
    vm.runInContext(code.slice(1, -1), ctx);
    if (step.press !== undefined) ctx.prompt.resolve(step.press);
    if (step.expire) ctx.timers[ctx.timers.length - 1].f();
    await tick(); await tick();
    report.push({ name: step.name, replies: [...out], prompt: ctx.prompt && { msg: ctx.prompt.msg, title: ctx.prompt.title },
                  timeoutMs: ctx.timers.length ? ctx.timers[ctx.timers.length - 1].ms : null });
  }
  console.log(JSON.stringify(report));
})();
