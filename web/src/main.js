// Verbindet Oberflaeche, Pose-Erkennung, Retargeting und 3D-Buehne.
import { Robot } from "./robot.js";
import { Stage } from "./stage.js";
import { retargetTrack, LiveRetargeter } from "./retarget.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

const state = {
  mode: "demo",          // demo | clip | live
  motion: null,          // { fps, qpos: Float64Array(36)[] }
  clock: 0, playing: true, busy: false,
  landmarker: null, live: null, stream: null, lastLive: 0, liveFps: 0,
};
let stage, robot;
const video = $("video");

// ---- Anzeige ---------------------------------------------------------------
function setStatus(title, sub = "") { $("stage-title").textContent = title; $("stage-sub").textContent = sub; }
function overlay(head, pct = null, step = "") {
  const o = $("overlay");
  if (head === null) { o.hidden = true; return; }
  o.hidden = false;
  $("overlay-head").textContent = head;
  $("overlay-pct").textContent = pct === null ? step : `${step} ${Math.round(pct * 100)}%`;
  $("overlay-bar").style.width = pct === null ? "0%" : `${(pct * 100).toFixed(1)}%`;
}
function stats(items) { $("stats").innerHTML = items.map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join(""); }
function fail(err) { console.error(err); $("error").textContent = err.message || String(err); overlay(null); state.busy = false; $("go-file").disabled = false; }

// ---- Bewegung abspielen ----------------------------------------------------
const tmp = new Float64Array(36);
function frameAt(m, t) {
  const last = m.qpos.length - 1, f = Math.max(0, Math.min(last, t * m.fps)), i = Math.floor(f), a = f - i;
  const q0 = m.qpos[i], q1 = m.qpos[Math.min(last, i + 1)];
  for (let k = 0; k < 36; k++) tmp[k] = q0[k] + a * (q1[k] - q0[k]);
  const n = Math.hypot(tmp[3], tmp[4], tmp[5], tmp[6]) || 1;
  for (let k = 3; k < 7; k++) tmp[k] /= n;
  return tmp;
}
const duration = (m) => (m.qpos.length - 1) / m.fps;

async function loadDemo(name, label) {
  stopLive();
  const d = await (await fetch(`./assets/motions/${name}.json`)).json();
  const qpos = [];
  for (let i = 0; i < d.frames; i++) qpos.push(Float64Array.from(d.qpos.slice(i * 36, i * 36 + 36)));
  state.motion = { fps: d.fps, qpos }; state.mode = "demo"; state.clock = 0; state.playing = true;
  video.pause(); video.removeAttribute("src"); $("inset").hidden = true;
  setStatus(label, "Demo motion, no video attached.");
  stats([[`${duration(state.motion).toFixed(1)} s`, "Clip length"], [d.frames, "Frames"], ["29", "Joints"], ["Demo", "Source"]]);
  syncPlayButton();
}

// ---- Video -> Bewegung -----------------------------------------------------
async function ensureLandmarker(size) {
  if (state.landmarker && state.landmarker.size === size) return state.landmarker;
  overlay("Loading the pose model.", null, "ONE-TIME DOWNLOAD");
  const { createLandmarker } = await import("./pose.js");
  state.landmarker = { ...(await createLandmarker(size)), size };
  return state.landmarker;
}

async function runClip(src, title, maxSeconds) {
  if (state.busy) return;
  state.busy = true; $("go-file").disabled = true; $("error").textContent = "";
  stopLive();
  try {
    const t0 = performance.now();
    const { lm, delegate } = await ensureLandmarker("heavy");
    const { extractTrack } = await import("./pose.js");
    overlay("Reading the moves.", 0, "POSE");
    video.srcObject = null; video.src = src; video.muted = true; video.loop = true; video.classList.remove("mirror");
    await new Promise((res, rej) => { video.onloadeddata = res; video.onerror = () => rej(new Error("This video format cannot be played by the browser.")); });
    $("inset").hidden = false;
    const track = await extractTrack(video, lm, { fps: 30, maxSeconds, onProgress: (p) => overlay("Reading the moves.", p, "POSE") });
    overlay("Teaching the robot.", 0, "RETARGET");
    await new Promise((r) => setTimeout(r, 30));
    const motion = retargetTrack(robot, track);
    state.motion = motion; state.mode = "clip"; state.playing = true; state.clipEnd = track.seconds;
    overlay(null);
    video.currentTime = 0; video.muted = false;
    video.play().catch(() => { video.muted = true; video.play(); });
    const hit = track.detected.filter(Boolean).length / track.detected.length;
    setStatus(title, "Original in the corner, robot on stage. Drag to orbit.");
    stats([[`${track.seconds.toFixed(1)} s`, "Clip length"], [track.world.length, "Frames"], [`${Math.round(hit * 100)}%`, "Dancer detected"],
      [`${((performance.now() - t0) / 1000).toFixed(1)} s`, `Processing (${delegate})`]]);
    syncPlayButton();
  } catch (e) { fail(e); return; }
  state.busy = false; $("go-file").disabled = false;
}

// ---- Webcam live -----------------------------------------------------------
async function startLive() {
  if (state.busy) return;
  state.busy = true; $("error").textContent = "";
  try {
    const { lm, delegate } = await ensureLandmarker("full");
    overlay("Waiting for the camera.", null, "ALLOW CAMERA ACCESS");
    state.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" }, audio: false });
    video.removeAttribute("src"); video.srcObject = state.stream; video.muted = true; video.classList.add("mirror");
    await video.play();
    $("inset").hidden = false; overlay(null);
    state.live = new LiveRetargeter(robot); state.mode = "live"; state.lastLive = 0; state.delegate = delegate;
    setStatus("Live", "Step back until your whole body is in frame. The robot mirrors you.");
    $("go-live").textContent = "Stop camera";
  } catch (e) { fail(e.name === "NotAllowedError" ? new Error("Camera access was denied.") : e); return; }
  state.busy = false;
}
function stopLive() {
  if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; video.srcObject = null; }
  state.live = null; $("go-live").textContent = "Start camera";
}
let liveTs = 0;
async function liveStep(now) {
  if (video.readyState < 2) return;
  const { toSim } = await import("./pose.js");
  liveTs = Math.max(liveTs + 1, Math.round(now));
  const sim = toSim(state.landmarker.lm.detectForVideo(video, liveTs), true);
  const dt = state.lastLive ? (now - state.lastLive) / 1000 : 1 / 30;
  state.lastLive = now;
  state.liveFps += 0.1 * (1 / Math.max(dt, 1e-3) - state.liveFps);
  if (sim) stage.setPose(state.live.step(sim.P, sim.vis, dt));
  stats([[state.liveFps.toFixed(0), "Poses per second"], [sim ? "Yes" : "No", "Dancer detected"], ["29", "Joints"], [state.delegate, "Pose runs on"]]);
}

// ---- Schleife --------------------------------------------------------------
let last = performance.now(), liveBusy = false;
function tick(now) {
  const dt = Math.min(0.1, (now - last) / 1000); last = now;
  if (state.mode === "live" && state.live) {
    if (!liveBusy) { liveBusy = true; liveStep(now).catch(fail).finally(() => { liveBusy = false; }); }
  } else if (state.motion) {
    let t;
    if (state.mode === "clip") {
      if (video.currentTime >= state.clipEnd) video.currentTime = 0;   // nur der verarbeitete Teil laeuft in Schleife
      t = video.currentTime;
    } else { if (state.playing) state.clock = (state.clock + dt) % duration(state.motion); t = state.clock; }
    stage.setPose(frameAt(state.motion, t));
  }
  stage.render(dt);
  requestAnimationFrame(tick);
}

// ---- Bedienung -------------------------------------------------------------
function syncPlayButton() { $("play").textContent = (state.mode === "clip" ? !video.paused : state.playing) ? "Pause" : "Play"; }
$("play").addEventListener("click", () => {
  if (state.mode === "clip") { video.paused ? video.play() : video.pause(); } else state.playing = !state.playing;
  setTimeout(syncPlayButton, 50);
});
document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => {
  stage.setView(b.dataset.view);
  document.querySelectorAll("[data-view]").forEach((c) => c.setAttribute("aria-pressed", c === b));
}));
document.querySelectorAll("[data-demo]").forEach((b) => b.addEventListener("click", () => loadDemo(b.dataset.demo, b.textContent.trim()).catch(fail)));

let picked = null;
const drop = $("drop");
const setFile = (f) => { picked = f; drop.classList.toggle("has", !!f); drop.textContent = f ? `${f.name} · ${(f.size / 1e6).toFixed(1)} MB` : "Drop a video file here or click to choose"; };
drop.addEventListener("click", () => $("file").click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") $("file").click(); });
$("file").addEventListener("change", (e) => setFile(e.target.files[0] || null));
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) setFile(f); });
$("length").addEventListener("click", (e) => {
  const b = e.target.closest(".chip"); if (!b) return;
  document.querySelectorAll("#length .chip").forEach((c) => c.setAttribute("aria-pressed", c === b));
});
const maxSeconds = () => { const s = document.querySelector('#length .chip[aria-pressed="true"]').dataset.s; return s ? Number(s) : null; };
$("go-file").addEventListener("click", () => {
  if (!picked) { $("error").textContent = "Choose a video file first."; return; }
  runClip(URL.createObjectURL(picked), picked.name.replace(/\.[^.]+$/, ""), maxSeconds());
});
$("go-live").addEventListener("click", () => { if (state.mode === "live") { stopLive(); loadDemo("test_dance", "Demo groove").catch(fail); } else startLive(); });

// Aufnahme der 3D-Ansicht als Video
let recorder = null;
$("record").addEventListener("click", () => {
  if (recorder) { recorder.stop(); return; }
  const stream = $("canvas").captureStream(30);
  if (state.mode === "clip" && video.captureStream) video.captureStream().getAudioTracks().forEach((t) => stream.addTrack(t));
  const type = ["video/mp4;codecs=avc1", "video/webm;codecs=vp9", "video/webm"].find((t) => MediaRecorder.isTypeSupported(t));
  const chunks = [];
  recorder = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 8e6 });
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(chunks, { type })); a.download = `robot-dance.${type.includes("mp4") ? "mp4" : "webm"}`; a.click();
    recorder = null; $("record").textContent = "Record"; $("record").classList.remove("on");
  };
  recorder.start(); $("record").textContent = "Stop recording"; $("record").classList.add("on");
});

// ---- Start -----------------------------------------------------------------
async function init() {
  overlay("Building the stage.", null, "LOADING");
  const [def, buf] = await Promise.all([fetch("./assets/scene.json").then((r) => r.json()), fetch("./assets/meshes.bin").then((r) => r.arrayBuffer())]);
  robot = new Robot(def.robot);
  stage = new Stage($("canvas"), def, buf, robot);
  window.__app = { stage, state, robot };
  overlay(null);
  await loadDemo("test_dance", "Demo groove");
  requestAnimationFrame(tick);
  // Entwicklung: ?video=/pfad/zum/video.mp4&seconds=8 verarbeitet ein Video ohne Dateidialog
  if (params.get("video")) runClip(params.get("video"), "Test video", Number(params.get("seconds")) || 8);
}
init().catch(fail);
