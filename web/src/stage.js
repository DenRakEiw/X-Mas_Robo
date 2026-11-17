// 3D-Buehne: baut die Weihnachtswelt und den G1 aus assets/scene.json mit three.js auf.
// Koordinaten wie in MuJoCo (z nach oben).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { toCreasedNormals } from "three/addons/utils/BufferGeometryUtils.js";

THREE.Object3D.DEFAULT_UP.set(0, 0, 1);

const VIEWS = {
  front: { pos: [3.3, -0.5, 1.15], fov: 46 },
  wide: { pos: [5.8, -1.4, 2.6], fov: 50 },
  side: { pos: [1.6, -3.4, 1.3], fov: 46 },
  top: { pos: [2.2, 0.6, 5.2], fov: 50 },
};
const quat = (q) => new THREE.Quaternion(q[1], q[2], q[3], q[0]);

function checker() {
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d");
  for (let y = 0; y < 2; y++) for (let x = 0; x < 2; x++) { g.fillStyle = (x + y) % 2 ? "#17171a" : "#0c0c0e"; g.fillRect(x * 128, y * 128, 128, 128); }
  g.strokeStyle = "#2c2c31"; g.lineWidth = 3; g.strokeRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(5, 5); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}

function makeMaterial(m) {
  const color = new THREE.Color(m.rgba[0], m.rgba[1], m.rgba[2]);
  if (m.name === "snow") return new THREE.MeshStandardMaterial({ color: 0xd9d9df, roughness: 0.95 });
  if (m.name === "stage") return new THREE.MeshStandardMaterial({ map: checker(), roughness: 0.28, metalness: 0.35 });
  const mat = new THREE.MeshStandardMaterial({ color, roughness: THREE.MathUtils.clamp(1 - 0.8 * m.shininess, 0.2, 1), metalness: 0.05 });
  if (m.emission > 0) { mat.emissive = color.clone(); mat.emissiveIntensity = m.emission >= 1 ? 1.35 : m.emission * 1.2; }
  return mat;
}

export class Stage {
  constructor(canvas, def, meshBuffer, robot) {
    this.canvas = canvas; this.robot = robot;
    const renderer = this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0;

    const scene = this.scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);
    scene.fog = new THREE.FogExp2(0x040405, 0.03);

    this.camera = new THREE.PerspectiveCamera(46, 16 / 9, 0.05, 120);
    this.camera.position.set(...VIEWS.front.pos);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, 0, 0.85);
    this.controls.enableDamping = true; this.controls.maxPolarAngle = Math.PI / 2 - 0.02;
    this.controls.minDistance = 1.2; this.controls.maxDistance = 14;
    this.follow = new THREE.Vector3(0, 0, 0.85);

    this._lights();
    this._meshes(def, meshBuffer);
    this._world(def.world);
    this._robot(def.robot);
    this._sky();

    this.composer = new EffectComposer(renderer);
    this.composer.addPass(new RenderPass(scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1280, 720), 0.3, 0.45, 0.95);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
  }

  _lights() {
    const s = this.scene;
    s.add(new THREE.HemisphereLight(0xa0a0b4, 0x1a1a1e, 0.32));
    const moon = new THREE.DirectionalLight(0xb4bad2, 0.3); moon.position.set(4, -5, 9); s.add(moon);
    const key = new THREE.SpotLight(0xfff6f0, 40, 14, 0.62, 0.7, 1.6);
    key.position.set(3.2, 1.8, 3.8); key.target.position.set(0, 0, 0.7);
    key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.camera.near = 1; key.shadow.camera.far = 12;
    s.add(key, key.target); this.key = key;
    const rim = new THREE.SpotLight(0xff3a7c, 30, 14, 0.75, 0.7, 1.6);
    rim.position.set(-2.6, -2.6, 3.0); rim.target.position.set(0, 0, 0.9); s.add(rim, rim.target); this.rim = rim;
    for (const [c, i, p] of [[0xff4f88, 7, [-3.6, 0.4, 3.2]], [0xff4f88, 4, [-4.4, 3.2, 1.6]], [0xffffff, 2.5, [-2.0, 0, 2.5]]]) {
      const l = new THREE.PointLight(c, i, 12, 1.7); l.position.set(...p); s.add(l);
    }
  }

  _meshes(def, buf) {
    this.geoms = def.meshes.map((m) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buf, m.vert[0], m.vert[1] * 3), 3));
      g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, m.face[0], m.face[1] * 3), 1));
      return g;
    });
  }

  _world(world) {
    const mats = world.materials.map(makeMaterial);
    const groups = new Map();
    const push = (type, mat, pos, q, scale) => {
      const key = `${type}|${mat}`;
      if (!groups.has(key)) groups.set(key, { type, mat, items: [] });
      groups.get(key).items.push({ pos, q, scale });
    };
    for (const g of world.geoms) {
      const m = world.materials[g.mat], [a, b, c] = g.size;
      if (m.name === "flake") continue;                       // Schnee faellt als Partikel
      const pos = new THREE.Vector3(...g.pos), q = quat(g.quat);
      if (g.type === "plane") {
        const floor = new THREE.Mesh(new THREE.CircleGeometry(70, 96), mats[g.mat]);
        floor.position.copy(pos); floor.receiveShadow = true; this.scene.add(floor);
      } else if (g.type === "mesh") {
        const geo = toCreasedNormals(this.geoms[g.mesh], 0.9);
        const mesh = new THREE.Mesh(geo, mats[g.mat]);
        mesh.position.copy(pos); mesh.quaternion.copy(q); mesh.castShadow = m.emission === 0; this.scene.add(mesh);
      } else if (g.type === "sphere") push("sphere", g.mat, pos, q, [a, a, a]);
      else if (g.type === "ellipsoid") push("sphere", g.mat, pos, q, [a, b, c]);
      else if (g.type === "box") push("box", g.mat, pos, q, [a, b, c]);
      else if (g.type === "cylinder") push("cylinder", g.mat, pos, q, [a, a, b]);
      else if (g.type === "capsule") {
        push("cylinder", g.mat, pos, q, [a, a, b]);
        for (const sgn of [1, -1]) push("sphere", g.mat, pos.clone().add(new THREE.Vector3(0, 0, sgn * b).applyQuaternion(q)), q, [a, a, a]);
      }
    }
    const base = {
      sphere: new THREE.SphereGeometry(1, 20, 14),
      box: new THREE.BoxGeometry(2, 2, 2),
      cylinder: new THREE.CylinderGeometry(1, 1, 2, 28).rotateX(Math.PI / 2),
    };
    const M = new THREE.Matrix4();
    for (const { type, mat, items } of groups.values()) {
      const inst = new THREE.InstancedMesh(base[type], mats[mat], items.length);
      items.forEach((it, i) => inst.setMatrixAt(i, M.compose(it.pos, it.q, new THREE.Vector3(...it.scale))));
      const m = world.materials[mat];
      inst.castShadow = m.emission === 0; inst.receiveShadow = m.name === "stage" || m.name.startsWith("snow");
      inst.frustumCulled = false;
      this.scene.add(inst);
    }
  }

  _robot(def) {
    this.parts = def.bodies.map((b) => {
      const grp = new THREE.Group(); grp.matrixAutoUpdate = false;
      for (const g of b.geoms) {
        const dark = g.rgba[0] < 0.4;
        const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(g.rgba[0], g.rgba[1], g.rgba[2]), roughness: dark ? 0.35 : 0.42, metalness: dark ? 0.5 : 0.12 });
        const mesh = new THREE.Mesh(toCreasedNormals(this.geoms[g.mesh], 0.7), mat);
        mesh.position.set(...g.pos); mesh.quaternion.copy(quat(g.quat)); mesh.castShadow = true; mesh.receiveShadow = true;
        grp.add(mesh);
      }
      this.scene.add(grp);
      return grp;
    });
    this.setPose(def.stand);
  }

  _sky() {
    const n = 1400, p = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2, e = Math.asin(Math.random() * 0.95 + 0.03), r = 60;
      p.set([r * Math.cos(e) * Math.cos(a), r * Math.cos(e) * Math.sin(a), r * Math.sin(e)], i * 3);
    }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(p, 3));
    this.scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, fog: false })));

    const m = 520, s = new Float32Array(m * 3);
    this.snowSeed = new Float32Array(m * 2);
    for (let i = 0; i < m; i++) { s.set([-9 + Math.random() * 16, -8 + Math.random() * 16, Math.random() * 7], i * 3); this.snowSeed.set([0.35 + Math.random() * 0.5, Math.random() * 6.28], i * 2); }
    const sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.BufferAttribute(s, 3));
    this.snow = new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xffffff, size: 0.05, transparent: true, opacity: 0.9, depthWrite: false }));
    this.scene.add(this.snow);
    this.time = 0;
  }

  /** qpos: Basis-Position (3), Basis-Quaternion wxyz (4), 29 Gelenkwinkel. */
  setPose(qpos) {
    const r = this.robot, q = qpos instanceof Float64Array ? qpos : Float64Array.from(qpos);
    r.fk(q.subarray(0, 3), [q[3], q[4], q[5], q[6]], q.subarray(7));
    for (let i = 0; i < this.parts.length; i++) {
      const R = r.R[i], p = r.p[i];
      this.parts[i].matrix.set(R[0], R[1], R[2], p[0], R[3], R[4], R[5], p[1], R[6], R[7], R[8], p[2], 0, 0, 0, 1);
      this.parts[i].matrixWorldNeedsUpdate = true;
    }
    this.pelvis = r.p[0];
  }

  setView(name) {
    const v = VIEWS[name]; if (!v) return;
    this.camera.position.set(v.pos[0] + this.follow.x, v.pos[1] + this.follow.y, v.pos[2]);
    this.camera.fov = v.fov; this.camera.updateProjectionMatrix();
    this.controls.target.copy(this.follow);
  }

  resize() {
    const el = this.canvas.parentElement, w = el.clientWidth, h = el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false); this.composer.setSize(w, h);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }

  render(dt) {
    this.time += dt;
    // Kamera folgt dem Becken, ohne die eigene Drehung des Betrachters zu stoeren
    if (this.pelvis) {
      const tx = this.pelvis[0], ty = this.pelvis[1], k = 1 - Math.exp(-dt / 0.35);
      const dx = (tx - this.follow.x) * k, dy = (ty - this.follow.y) * k;
      this.follow.x += dx; this.follow.y += dy;
      this.controls.target.x += dx; this.controls.target.y += dy;
      this.camera.position.x += dx; this.camera.position.y += dy;
      this.key.target.position.set(this.follow.x, this.follow.y, 0.7); this.rim.target.position.set(this.follow.x, this.follow.y, 0.9);
    }
    const p = this.snow.geometry.attributes.position, a = p.array;
    for (let i = 0; i < p.count; i++) {
      a[i * 3 + 2] -= this.snowSeed[i * 2] * dt;
      a[i * 3] += 0.15 * Math.sin(this.time * 0.9 + this.snowSeed[i * 2 + 1]) * dt;
      if (a[i * 3 + 2] < 0) a[i * 3 + 2] = 7;
    }
    p.needsUpdate = true;
    this.controls.update();
    this.composer.render();
  }
}
