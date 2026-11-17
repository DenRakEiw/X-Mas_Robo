// Pose-Erkennung im Browser mit MediaPipe Pose Landmarker (wird erst bei Bedarf geladen).
const VERSION = "0.10.14";
const BUNDLE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}/vision_bundle.mjs`;
const WASM = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}/wasm`;
const MODEL = (size) => `https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_${size}/float16/latest/pose_landmarker_${size}.task`;

// Paare links/rechts fuer die Spiegelung
const SWAP = [0, 4, 5, 6, 1, 2, 3, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19, 22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31];

/** size: "heavy" (genau), "full" (schneller) oder "lite". */
export async function createLandmarker(size = "heavy") {
  const { FilesetResolver, PoseLandmarker } = await import(BUNDLE);
  const files = await FilesetResolver.forVisionTasks(WASM);
  const make = (delegate) => PoseLandmarker.createFromOptions(files, {
    baseOptions: { modelAssetPath: MODEL(size), delegate },
    runningMode: "VIDEO", numPoses: 1,
    minPoseDetectionConfidence: 0.5, minPosePresenceConfidence: 0.5, minTrackingConfidence: 0.5,
  });
  try { return { lm: await make("GPU"), delegate: "GPU" }; }
  catch { return { lm: await make("CPU"), delegate: "CPU" }; }
}

/** MediaPipe-Welt (x rechts, y unten, z von der Kamera weg) -> Sim (x vorn, y links, z oben). */
export function toSim(result, mirror = false) {
  const w = result.worldLandmarks && result.worldLandmarks[0];
  if (!w) return null;
  const P = new Array(33), vis = new Float64Array(33);
  for (let i = 0; i < 33; i++) {
    const p = w[mirror ? SWAP[i] : i];
    P[i] = [-p.z, mirror ? -p.x : p.x, -p.y];
    vis[i] = p.visibility ?? 1;
  }
  return { P, vis };
}

const seek = (video, t) => new Promise((resolve) => {
  const done = () => { video.removeEventListener("seeked", done); clearTimeout(timer); resolve(); };
  const timer = setTimeout(done, 1500);
  video.addEventListener("seeked", done);
  video.currentTime = t;
});

/** Geht das Video Bild fuer Bild durch und liefert die Pose-Spur fuer retargetTrack(). */
export async function extractTrack(video, lm, { fps = 30, maxSeconds = null, onProgress = null } = {}) {
  video.pause();
  const dur = Math.min(video.duration, maxSeconds || Infinity), n = Math.max(1, Math.floor(dur * fps));
  const world = [], vis = [], detected = [];
  const t0 = performance.now();
  for (let i = 0; i < n; i++) {
    await seek(video, i / fps);
    const sim = toSim(lm.detectForVideo(video, Math.round(t0 + (i * 1000) / fps)));
    if (sim) { world.push(Float64Array.from(sim.P.flat())); vis.push(sim.vis); detected.push(true); }
    else { world.push(new Float64Array(99)); vis.push(new Float64Array(33)); detected.push(false); }
    if (onProgress && i % 5 === 0) onProgress(i / n);
  }
  return { fps, world, vis, detected, seconds: n / fps };
}
