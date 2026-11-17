// Vergleicht das JavaScript-Retargeting mit dem Python-Ergebnis fuer dieselben Pose-Daten.
//   node web/test/retarget.test.mjs
// fixture.json entsteht mit: .venv/Scripts/python tools/dump_pose_test.py <video> 6
import { readFileSync } from "node:fs";
import { Robot } from "../src/robot.js";
import { retargetTrack } from "../src/retarget.js";

const here = new URL(".", import.meta.url);
const scene = JSON.parse(readFileSync(new URL("../assets/scene.json", here)));
const fx = JSON.parse(readFileSync(new URL("./fixture.json", here)));

const robot = new Robot(scene.robot);
const t0 = performance.now();
const { qpos } = retargetTrack(robot, { fps: fx.fps, world: fx.world, vis: fx.vis, detected: fx.detected });
const ms = performance.now() - t0;

let maxJoint = 0, maxRoot = 0, maxQuat = 0, sumJoint = 0, n = 0;
qpos.forEach((q, i) => {
  const ref = fx.qpos[i];
  for (let k = 0; k < 3; k++) maxRoot = Math.max(maxRoot, Math.abs(q[k] - ref[k]));
  const sg = q[3] * ref[3] + q[4] * ref[4] + q[5] * ref[5] + q[6] * ref[6] < 0 ? -1 : 1;
  const dq = Math.hypot(q[3] - sg * ref[3], q[4] - sg * ref[4], q[5] - sg * ref[5], q[6] - sg * ref[6]);
  maxQuat = Math.max(maxQuat, 2 * dq);   // Winkel fuer kleine Unterschiede, stabil bei gerundeten Vergleichsdaten
  for (let k = 7; k < 36; k++) { const d = Math.abs(q[k] - ref[k]); maxJoint = Math.max(maxJoint, d); sumJoint += d; n++; }
});
console.log(`${qpos.length} Bilder in ${ms.toFixed(0)} ms (${(ms / qpos.length).toFixed(2)} ms je Bild, zwei Durchgaenge)`);
console.log(`Gelenke: max ${maxJoint.toFixed(4)} rad, Mittel ${(sumJoint / n).toFixed(5)} rad`);
console.log(`Basis: Position max ${(maxRoot * 1000).toFixed(2)} mm, Drehung max ${maxQuat.toFixed(5)} rad`);
const ok = maxJoint < 0.02 && maxRoot < 0.005 && maxQuat < 0.005;
console.log(ok ? "OK: JavaScript und Python stimmen ueberein" : "FEHLER: Abweichung zu gross");
process.exit(ok ? 0 : 1);
