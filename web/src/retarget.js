// Uebertraegt menschliche Koerperpunkte (MediaPipe, 33 Punkte) auf die Gelenke des G1.
// JavaScript-Fassung von app/retarget.py; test/retarget.test.mjs vergleicht beide.
import { matToQuat } from "./robot.js";

export const LM = { L_SH: 11, R_SH: 12, L_EL: 13, R_EL: 14, L_WR: 15, R_WR: 16, L_HIP: 23, R_HIP: 24, L_KN: 25, R_KN: 26, L_AN: 27, R_AN: 28, L_HEEL: 29, R_HEEL: 30, L_TOE: 31, R_TOE: 32 };
const SIDES = {
  left: [LM.L_SH, LM.L_EL, LM.L_WR, LM.L_HIP, LM.L_KN, LM.L_AN, LM.L_HEEL, LM.L_TOE],
  right: [LM.R_SH, LM.R_EL, LM.R_WR, LM.R_HIP, LM.R_KN, LM.R_AN, LM.R_HEEL, LM.R_TOE],
};
const W_POS = 12, W_TORSO = 1.5, W_FOOT = 0.5, W_REST = 0.03, W_WRIST = 0.3, W_PREV = 0.08, DAMP = 1e-3;
const MAX_SPEED = 14; // rad/s
const SOLE_R = 0.005;
const SOLE = [[-0.05, 0.025, -0.03], [-0.05, -0.025, -0.03], [0.12, 0.03, -0.03], [0.12, -0.03, -0.03]];

// ---- kleine Vektorhilfen
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) + 1e-9; return [a[0] / l, a[1] / l, a[2] / l]; };
const mix = (a, b, t) => norm([t * a[0] + (1 - t) * b[0], t * a[1] + (1 - t) * b[1], t * a[2] + (1 - t) * b[2]]);
const col = (R, c) => [R[c], R[3 + c], R[6 + c]];
const smoothstep = (v, lo, hi) => { const t = Math.min(1, Math.max(0, (v - lo) / (hi - lo))); return t * t * (3 - 2 * t); };

/** Rotationsmatrix mit Spalten x (vorn), y (links), z (oben). */
function frame(y, up) {
  y = norm(y);
  const x = norm(cross(y, up)), z = cross(x, y);
  return [x[0], y[0], z[0], x[1], y[1], z[1], x[2], y[2], z[2]];
}

/** Drehvektor von Rc nach Rt im Weltsystem: log(Rt * Rc^T). */
function rotErr(Rt, Rc) {
  const m = new Array(9);
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) m[i * 3 + j] = Rt[i * 3] * Rc[j * 3] + Rt[i * 3 + 1] * Rc[j * 3 + 1] + Rt[i * 3 + 2] * Rc[j * 3 + 2];
  const c = Math.min(1, Math.max(-1, (m[0] + m[4] + m[8] - 1) / 2));
  const ang = Math.acos(c);
  const v = [m[7] - m[5], m[2] - m[6], m[3] - m[1]];
  if (ang < 1e-6) return scale(v, 0.5);
  if (Math.PI - ang < 1e-3) { // nahe 180 Grad: Achse aus der Diagonale
    const ax = norm([Math.sqrt(Math.max(0, (m[0] + 1) / 2)), Math.sqrt(Math.max(0, (m[4] + 1) / 2)), Math.sqrt(Math.max(0, (m[8] + 1) / 2))]);
    return scale(ax, ang);
  }
  return scale(v, ang / (2 * Math.sin(ang)));
}

/** Loest A x = b fuer symmetrisch positiv definites A (Cholesky), A wird ueberschrieben. */
function solveSPD(A, b, n) {
  for (let i = 0; i < n; i++) {
    for (let j = 0; j <= i; j++) {
      let s = A[i * n + j];
      for (let k = 0; k < j; k++) s -= A[i * n + k] * A[j * n + k];
      A[i * n + j] = i === j ? Math.sqrt(Math.max(s, 1e-12)) : s / A[j * n + j];
    }
  }
  const x = new Float64Array(n);
  for (let i = 0; i < n; i++) { let s = b[i]; for (let k = 0; k < i; k++) s -= A[i * n + k] * x[k]; x[i] = s / A[i * n + i]; }
  for (let i = n - 1; i >= 0; i--) { let s = x[i]; for (let k = i + 1; k < n; k++) s -= A[k * n + i] * x[k]; x[i] = s / A[i * n + i]; }
  return x;
}

export class Retargeter {
  constructor(robot) {
    this.r = robot;
    const b = robot.byName, nj = robot.nj;
    this.nj = nj;
    this.torso = b.torso_link;
    this.side = {};
    for (const s of ["left", "right"]) {
      this.side[s] = { shoulder: b[`${s}_shoulder_roll_link`], elbow: b[`${s}_elbow_link`], wrist: b[`${s}_wrist_yaw_link`], hip: b[`${s}_hip_roll_link`], knee: b[`${s}_knee_link`], foot: b[`${s}_ankle_roll_link`] };
    }
    this.lo = robot.lo.map((v) => v + 0.02); this.hi = robot.hi.map((v) => v - 0.02);
    this.restW = new Float64Array(nj).fill(W_REST);
    robot.jointNames.forEach((n, j) => { if (n.includes("wrist")) this.restW[j] = W_WRIST; });

    this.q = new Float64Array(nj);
    robot.fk([0, 0, 0], [1, 0, 0, 0], this.q);
    const d = (a, c) => Math.hypot(...sub(robot.p[a], robot.p[c]));
    this.len = {};
    for (const [s, c] of Object.entries(this.side)) this.len[s] = { upper: d(c.elbow, c.shoulder), fore: d(c.wrist, c.elbow), thigh: d(c.knee, c.hip), shank: d(c.foot, c.knee) };
    this.first = true;
    this.A = new Float64Array(nj * nj); this.b = new Float64Array(nj); this.cols = new Float64Array(nj * 3);
    this.quat = [1, 0, 0, 0];
  }

  _task(e, w) { // fuegt eine 3-zeilige Aufgabe mit Jacobi this.cols hinzu
    const { A, b, cols, nj } = this, w2 = w * w;
    for (let j = 0; j < nj; j++) {
      const cx = cols[j * 3], cy = cols[j * 3 + 1], cz = cols[j * 3 + 2];
      if (cx === 0 && cy === 0 && cz === 0) continue;
      b[j] += w2 * (cx * e[0] + cy * e[1] + cz * e[2]);
      for (let k = 0; k <= j; k++) A[j * nj + k] += w2 * (cx * cols[k * 3] + cy * cols[k * 3 + 1] + cz * cols[k * 3 + 2]);
    }
  }

  solePoints(s) {
    const f = this.side[s].foot, R = this.r.R[f], p = this.r.p[f];
    return SOLE.map((v) => [p[0] + R[0] * v[0] + R[1] * v[1] + R[2] * v[2], p[1] + R[3] * v[0] + R[4] * v[1] + R[5] * v[2], p[2] + R[6] * v[0] + R[7] * v[1] + R[8] * v[2]]);
  }

  /** P: 33 Punkte [x,y,z] in Sim-Koordinaten, vis: 33 Sichtbarkeiten. Ergebnis: qpos (36) mit Basis im Ursprung. */
  solve(P, vis, flatFeet = [false, false], dt = 1 / 30) {
    const r = this.r, nj = this.nj, up = [0, 0, 1];
    const hipMid = scale(add(P[LM.L_HIP], P[LM.R_HIP]), 0.5), shMid = scale(add(P[LM.L_SH], P[LM.R_SH]), 0.5);
    const spine = norm(sub(shMid, hipMid));
    let Rp = frame(sub(P[LM.L_HIP], P[LM.R_HIP]), spine);
    Rp = frame(col(Rp, 1), norm(add(spine, up)));   // Becken nur halb mitneigen, Rest macht die Taille
    const Rt = frame(sub(P[LM.L_SH], P[LM.R_SH]), spine);
    this.quat = matToQuat(Rp);

    const down = scale(col(Rp, 2), -1), fwd = col(Rp, 0), restArm = scale(col(Rt, 2), -1);
    const tgt = {};
    Object.entries(SIDES).forEach(([s, [sh, el, wr, hp, kn, an, heel, toe]], k) => {
      const aArm = smoothstep(Math.min(vis[el], vis[wr]), 0.25, 0.6), aLeg = smoothstep(Math.min(vis[kn], vis[an]), 0.25, 0.6);
      let fx = mix(norm(sub(P[toe], P[heel])), fwd, aLeg);
      if (flatFeet[k]) fx = norm([fx[0], fx[1], 0]);
      const fy = cross(up, fx);
      tgt[s] = {
        upper: mix(norm(sub(P[el], P[sh])), restArm, aArm), fore: mix(norm(sub(P[wr], P[el])), restArm, aArm),
        thigh: mix(norm(sub(P[kn], P[hp])), down, aLeg), shank: mix(norm(sub(P[an], P[kn])), down, aLeg),
        foot: frame(fy, cross(fx, fy)),
      };
    });

    const qPrev = Float64Array.from(this.q), { A, b, cols } = this;
    const iters = this.first ? 40 : 8, maxStep = MAX_SPEED * dt;
    for (let it = 0; it < iters; it++) {
      r.fk([0, 0, 0], this.quat, this.q);
      A.fill(0); b.fill(0);

      cols.fill(0); r.addJacR(this.torso, cols);
      this._task(rotErr(Rt, r.R[this.torso]), W_TORSO);

      for (const [s, c] of Object.entries(this.side)) {
        const L = this.len[s], t = tgt[s];
        for (const [a, e, key] of [["shoulder", "elbow", "upper"], ["elbow", "wrist", "fore"], ["hip", "knee", "thigh"], ["knee", "foot", "shank"]]) {
          cols.fill(0); r.addJacP(c[e], cols, 1); r.addJacP(c[a], cols, -1);
          this._task(sub(scale(t[key], L[key]), sub(r.p[c[e]], r.p[c[a]])), W_POS);
        }
        cols.fill(0); r.addJacR(c.foot, cols);
        this._task(rotErr(t.foot, r.R[c.foot]), W_FOOT);
      }
      for (let j = 0; j < nj; j++) {
        const w2 = this.restW[j] * this.restW[j];
        A[j * nj + j] += w2 + DAMP; b[j] -= w2 * this.q[j];
        if (!this.first) { A[j * nj + j] += W_PREV * W_PREV; b[j] += W_PREV * W_PREV * (qPrev[j] - this.q[j]); }
      }
      const dq = solveSPD(A, b, nj);
      for (let j = 0; j < nj; j++) {
        let v = Math.min(this.hi[j], Math.max(this.lo[j], this.q[j] + dq[j]));
        if (!this.first) v = Math.min(qPrev[j] + maxStep, Math.max(qPrev[j] - maxStep, v));
        this.q[j] = v;
      }
    }
    this.first = false;
    r.fk([0, 0, 0], this.quat, this.q);
    const out = new Float64Array(36);
    out.set(this.quat, 3); out.set(this.q, 7);
    return out;
  }
}

// ---- Offline: ganzer Clip mit Glaettung und Standfuss-Verankerung ------------------------------

function gauss1d(x, sigma) { // wie scipy gaussian_filter1d, mode="nearest", truncate=4
  const n = x.length, rad = Math.max(1, Math.floor(4 * sigma + 0.5)), k = new Float64Array(2 * rad + 1);
  let sum = 0;
  for (let i = -rad; i <= rad; i++) { k[i + rad] = Math.exp(-0.5 * (i / sigma) ** 2); sum += k[i + rad]; }
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    let s = 0;
    for (let j = -rad; j <= rad; j++) s += k[j + rad] * x[Math.min(n - 1, Math.max(0, i + j))];
    out[i] = s / sum;
  }
  return out;
}

function smoothColumns(rows, width, sigma) { // rows: Array von Float64Array(width)
  const n = rows.length, tmp = new Float64Array(n);
  for (let c = 0; c < width; c++) {
    for (let i = 0; i < n; i++) tmp[i] = rows[i][c];
    const s = gauss1d(tmp, sigma);
    for (let i = 0; i < n; i++) rows[i][c] = s[i];
  }
}

function fillGaps(rows, ok, width) {
  const good = [];
  ok.forEach((v, i) => { if (v) good.push(i); });
  for (let i = 0; i < rows.length; i++) {
    if (ok[i]) continue;
    let hi = good.findIndex((g) => g > i), lo;
    if (hi === -1) { lo = hi = good[good.length - 1]; } else if (hi === 0) { lo = hi = good[0]; } else { lo = good[hi - 1]; hi = good[hi]; }
    const t = hi === lo ? 0 : (i - lo) / (hi - lo);
    for (let c = 0; c < width; c++) rows[i][c] = rows[lo][c] * (1 - t) + rows[hi][c] * t;
  }
}

const median = (a) => { const s = Float64Array.from(a).sort(); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

/**
 * track: { fps, world: Float64Array(99)[] (Sim-Koordinaten), vis: Float64Array(33)[], detected: bool[] }
 * Ergebnis: { fps, qpos: Float64Array(36)[] }
 */
export function retargetTrack(robot, track, onProgress = null, stageRadius = 1.9) {
  const fps = track.fps, T = track.world.length;
  if (track.detected.filter(Boolean).length < 5) throw new Error("Hardly any person detected in this video");
  const world = track.world.map((w) => Float64Array.from(w)), vis = track.vis.map((v) => Float64Array.from(v));
  fillGaps(world, track.detected, 99); fillGaps(vis, track.detected, 33);

  // gekippte Kamera ausgleichen (hoechstens 25 Grad)
  const sx = [], sz = [];
  for (const w of world) {
    sx.push(0.5 * (w[LM.L_SH * 3] + w[LM.R_SH * 3]) - 0.5 * (w[LM.L_HIP * 3] + w[LM.R_HIP * 3]));
    sz.push(0.5 * (w[LM.L_SH * 3 + 2] + w[LM.R_SH * 3 + 2]) - 0.5 * (w[LM.L_HIP * 3 + 2] + w[LM.R_HIP * 3 + 2]));
  }
  const lim = (25 * Math.PI) / 180, ang = -Math.min(lim, Math.max(-lim, Math.atan2(median(sx), median(sz))));
  const c = Math.cos(ang), s = Math.sin(ang);
  for (const w of world) for (let i = 0; i < 33; i++) { const x = w[i * 3], z = w[i * 3 + 2]; w[i * 3] = c * x + s * z; w[i * 3 + 2] = -s * x + c * z; }

  smoothColumns(world, 99, Math.max(0.8, fps * 0.045));
  smoothColumns(vis, 33, fps * 0.15);
  const pts = world.map((w) => Array.from({ length: 33 }, (_, i) => [w[i * 3], w[i * 3 + 1], w[i * 3 + 2]]));

  const qpos = new Array(T), low = new Array(T), centers = new Array(T);
  const measure = (rt, i) => {
    const sl = [rt.solePoints("left"), rt.solePoints("right")];
    low[i] = sl.map((p) => Math.min(...p.map((v) => v[2])));
    centers[i] = sl.map((p) => [p.reduce((a, v) => a + v[0], 0) / 4, p.reduce((a, v) => a + v[1], 0) / 4]);
  };
  let rt = new Retargeter(robot);
  for (let i = 0; i < T; i++) { rt.solve(pts[i], vis[i], [false, false], 1 / fps); measure(rt, i); if (onProgress && i % 20 === 0) onProgress(0.5 * i / T); }
  // zweiter Durchgang: Fuesse nahe am Boden stehen flach
  const near = low.map((l) => { const g = Math.min(l[0], l[1]); return [l[0] - g < 0.03, l[1] - g < 0.03]; });
  rt = new Retargeter(robot);
  for (let i = 0; i < T; i++) { qpos[i] = rt.solve(pts[i], vis[i], near[i], 1 / fps); measure(rt, i); if (onProgress && i % 20 === 0) onProgress(0.5 + 0.5 * i / T); }

  const jointRows = qpos.map((q) => q.subarray(7));
  smoothColumns(jointRows, 29, Math.max(0.6, fps * 0.03));

  const z = gauss1d(low.map((l) => -(Math.min(l[0], l[1]) - SOLE_R)), Math.max(0.6, fps * 0.04));

  // Standfuss-Verankerung
  const xs = new Float64Array(T), ys = new Float64Array(T);
  let sup = low[0][0] <= low[0][1] ? 0 : 1, anchor = [...centers[0][sup]];
  for (let i = 0; i < T; i++) {
    const other = 1 - sup;
    if (low[i][other] < low[i][sup] - 0.02) {
      anchor = i ? [xs[i - 1] + centers[i][other][0], ys[i - 1] + centers[i][other][1]] : [...centers[i][other]];
      sup = other;
    }
    xs[i] = anchor[0] - centers[i][sup][0]; ys[i] = anchor[1] - centers[i][sup][1];
  }
  const drift = [gauss1d(xs, fps * 2.5), gauss1d(ys, fps * 2.5)];
  for (let i = 0; i < T; i++) { xs[i] -= drift[0][i]; ys[i] -= drift[1][i]; }
  const fx = gauss1d(xs, Math.max(0.6, fps * 0.04)), fy = gauss1d(ys, Math.max(0.6, fps * 0.04));
  for (let i = 0; i < T; i++) {
    const rr = Math.hypot(fx[i], fy[i]), k = Math.min(1, stageRadius / Math.max(rr, 1e-6));
    qpos[i][0] = fx[i] * k; qpos[i][1] = fy[i] * k; qpos[i][2] = z[i];
  }
  return { fps, qpos };
}

// ---- Live: Bild fuer Bild, nur mit Blick in die Vergangenheit ------------------------------------

export class LiveRetargeter {
  constructor(robot) {
    this.rt = new Retargeter(robot);
    this.P = null; this.vis = null;
    this.z = 0.79; this.xy = [0, 0]; this.sup = 0; this.anchor = null;
  }

  /** P: 33 Punkte (Sim-Koordinaten), vis: 33, dt in Sekunden. Liefert qpos (36). */
  step(P, vis, dt) {
    dt = Math.min(0.1, Math.max(1 / 120, dt));
    const a = 1 - Math.exp(-dt / 0.06);   // Glaettung der Punkte, Zeitkonstante 60 ms
    if (!this.P) { this.P = P.map((p) => [...p]); this.vis = Float64Array.from(vis); }
    else for (let i = 0; i < 33; i++) {
      for (let k = 0; k < 3; k++) this.P[i][k] += a * (P[i][k] - this.P[i][k]);
      this.vis[i] += 0.3 * (vis[i] - this.vis[i]);
    }
    const rt = this.rt;
    rt.solve(this.P, this.vis, [false, false], dt);
    const sl = [rt.solePoints("left"), rt.solePoints("right")];
    const low = sl.map((p) => Math.min(...p.map((v) => v[2])));
    const g = Math.min(low[0], low[1]);
    const q = rt.solve(this.P, this.vis, [low[0] - g < 0.03, low[1] - g < 0.03], dt);

    const sl2 = [rt.solePoints("left"), rt.solePoints("right")];
    const low2 = sl2.map((p) => Math.min(...p.map((v) => v[2])));
    const cen = sl2.map((p) => [p.reduce((s, v) => s + v[0], 0) / 4, p.reduce((s, v) => s + v[1], 0) / 4]);
    const zt = -(Math.min(low2[0], low2[1]) - SOLE_R);
    this.z += (1 - Math.exp(-dt / 0.08)) * (zt - this.z);

    if (!this.anchor) { this.sup = low2[0] <= low2[1] ? 0 : 1; this.anchor = [...cen[this.sup]]; }
    const other = 1 - this.sup;
    if (low2[other] < low2[this.sup] - 0.02) { this.anchor = [this.xy[0] + cen[other][0], this.xy[1] + cen[other][1]]; this.sup = other; }
    const tx = this.anchor[0] - cen[this.sup][0], ty = this.anchor[1] - cen[this.sup][1];
    // langsam zur Buehnenmitte zurueckziehen, damit nichts wegdriftet
    const leak = Math.exp(-dt / 4);
    this.anchor[0] -= tx * (1 - leak); this.anchor[1] -= ty * (1 - leak);
    const b = 1 - Math.exp(-dt / 0.08);
    this.xy[0] += b * (tx - this.xy[0]); this.xy[1] += b * (ty - this.xy[1]);
    q[0] = this.xy[0]; q[1] = this.xy[1]; q[2] = this.z;
    return q;
  }
}
