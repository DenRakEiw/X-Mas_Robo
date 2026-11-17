// Kinematik des Unitree G1: Vorwaertskinematik und Jacobi-Spalten, ohne Abhaengigkeiten.
// Laeuft im Browser und (fuer Tests) in Node. Koordinaten wie in MuJoCo: x vorn, y links, z oben.
// Rotationen sind 3x3-Matrizen als Array mit 9 Zahlen, zeilenweise.

export const quatToMat = (q, out = new Float64Array(9)) => {
  const [w, x, y, z] = q;
  out[0] = 1 - 2 * (y * y + z * z); out[1] = 2 * (x * y - w * z); out[2] = 2 * (x * z + w * y);
  out[3] = 2 * (x * y + w * z); out[4] = 1 - 2 * (x * x + z * z); out[5] = 2 * (y * z - w * x);
  out[6] = 2 * (x * z - w * y); out[7] = 2 * (y * z + w * x); out[8] = 1 - 2 * (x * x + y * y);
  return out;
};

export const matToQuat = (m) => {
  const tr = m[0] + m[4] + m[8];
  let w, x, y, z;
  if (tr > 0) { const s = Math.sqrt(tr + 1) * 2; w = s / 4; x = (m[7] - m[5]) / s; y = (m[2] - m[6]) / s; z = (m[3] - m[1]) / s; }
  else if (m[0] > m[4] && m[0] > m[8]) { const s = Math.sqrt(1 + m[0] - m[4] - m[8]) * 2; w = (m[7] - m[5]) / s; x = s / 4; y = (m[1] + m[3]) / s; z = (m[2] + m[6]) / s; }
  else if (m[4] > m[8]) { const s = Math.sqrt(1 + m[4] - m[0] - m[8]) * 2; w = (m[2] - m[6]) / s; x = (m[1] + m[3]) / s; y = s / 4; z = (m[5] + m[7]) / s; }
  else { const s = Math.sqrt(1 + m[8] - m[0] - m[4]) * 2; w = (m[3] - m[1]) / s; x = (m[2] + m[6]) / s; y = (m[5] + m[7]) / s; z = s / 4; }
  return w < 0 ? [-w, -x, -y, -z] : [w, x, y, z];
};

export const matMul = (a, b, out) => {
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++)
    out[i * 3 + j] = a[i * 3] * b[j] + a[i * 3 + 1] * b[3 + j] + a[i * 3 + 2] * b[6 + j];
  return out;
};

const axisAngle = (ax, ang, out) => {
  const [x, y, z] = ax, c = Math.cos(ang), s = Math.sin(ang), t = 1 - c;
  out[0] = t * x * x + c; out[1] = t * x * y - s * z; out[2] = t * x * z + s * y;
  out[3] = t * x * y + s * z; out[4] = t * y * y + c; out[5] = t * y * z - s * x;
  out[6] = t * x * z - s * y; out[7] = t * y * z + s * x; out[8] = t * z * z + c;
  return out;
};

export class Robot {
  constructor(def) {
    this.bodies = def.bodies.map((b) => ({ ...b, R0: quatToMat(b.quat) }));
    this.n = this.bodies.length;
    this.nj = this.bodies.filter((b) => b.joint).length;
    this.byName = Object.fromEntries(this.bodies.map((b, i) => [b.name, i]));
    this.lo = new Float64Array(this.nj); this.hi = new Float64Array(this.nj);
    this.jointBody = new Int32Array(this.nj);
    this.jointNames = new Array(this.nj);
    this.bodies.forEach((b, i) => {
      if (!b.joint) return;
      this.jointBody[b.joint.index] = i;
      this.jointNames[b.joint.index] = b.joint.name;
      this.lo[b.joint.index] = b.joint.range[0]; this.hi[b.joint.index] = b.joint.range[1];
    });
    // Gelenke auf dem Weg von der Basis zu jedem Koerper
    this.chain = this.bodies.map((_, i) => {
      const js = [];
      for (let b = i; b >= 0; b = this.bodies[b].parent) if (this.bodies[b].joint) js.push(this.bodies[b].joint.index);
      return js;
    });
    this.R = this.bodies.map(() => new Float64Array(9));   // Weltrotation je Koerper
    this.p = this.bodies.map(() => new Float64Array(3));   // Weltposition je Koerper
    this.axis = Array.from({ length: this.nj }, () => new Float64Array(3)); // Gelenkachse in der Welt
    this._a = new Float64Array(9); this._b = new Float64Array(9);
  }

  /** Vorwaertskinematik. rootPos (3), rootQuat (wxyz), q (Gelenkwinkel). */
  fk(rootPos, rootQuat, q) {
    for (let i = 0; i < this.n; i++) {
      const b = this.bodies[i], R = this.R[i], p = this.p[i];
      if (b.parent < 0) { quatToMat(rootQuat, R); p[0] = rootPos[0]; p[1] = rootPos[1]; p[2] = rootPos[2]; continue; }
      const Rp = this.R[b.parent], pp = this.p[b.parent];
      for (let k = 0; k < 3; k++) p[k] = pp[k] + Rp[k * 3] * b.pos[0] + Rp[k * 3 + 1] * b.pos[1] + Rp[k * 3 + 2] * b.pos[2];
      matMul(Rp, b.R0, this._a);
      if (b.joint) {
        matMul(this._a, axisAngle(b.joint.axis, q[b.joint.index], this._b), R);
        const ax = this.axis[b.joint.index], a = b.joint.axis;
        for (let k = 0; k < 3; k++) ax[k] = R[k * 3] * a[0] + R[k * 3 + 1] * a[1] + R[k * 3 + 2] * a[2];
      } else R.set(this._a);
    }
  }

  /** Addiert sign * Positions-Jacobi des Koerperursprungs in cols (3 Zahlen je Gelenk). */
  addJacP(body, cols, sign = 1) {
    const pb = this.p[body];
    for (const j of this.chain[body]) {
      const a = this.axis[j], o = this.p[this.jointBody[j]];
      const dx = pb[0] - o[0], dy = pb[1] - o[1], dz = pb[2] - o[2];
      cols[j * 3] += sign * (a[1] * dz - a[2] * dy);
      cols[j * 3 + 1] += sign * (a[2] * dx - a[0] * dz);
      cols[j * 3 + 2] += sign * (a[0] * dy - a[1] * dx);
    }
  }

  /** Addiert die Rotations-Jacobi des Koerpers in cols. */
  addJacR(body, cols) {
    for (const j of this.chain[body]) {
      const a = this.axis[j];
      cols[j * 3] += a[0]; cols[j * 3 + 1] += a[1]; cols[j * 3 + 2] += a[2];
    }
  }
}
