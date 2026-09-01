/**
 * office-scene.js — Marvis 风格极简白办公室 (P7 v3)
 * v3: OrbitControls 交互 / 4列工位+中央共享区(玻璃护栏) / 背后屋顶视角 /
 *     Agent 落座椅子 / 猫定时巡逻 / Agent 递文件动画(数据传递可视化)。
 * 渲染 = OfficeState 的投影；本模块不持有业务状态。
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { PetEcosystem } from './pet-ecosystem.js';

const C = {
  bg: 0xf4f5f6, floor: 0xffffff, furniture: 0xf7f7f8,
  agent: 0x1c1c1e,
  // IT 界蓝屏 = 故障；屏幕一律黑色系（开机=深灰微亮，关机=纯黑）
  screenOn: 0x16171b, screenOff: 0x0a0a0c,
};

// 6 列工位，中央留共享区走廊（x ∈ [-2.4, 2.4]）
const COL_X = [-16.0, -10.5, -5.0, 5.0, 10.5, 16.0];
// ROW_DZ 拉大到 6.5：同列桌子前后间隙 ~3.6（桌+椅进深约 2.9），
// 让猫沿外侧工位列穿行时能明显看到它在桌与桌之间走动。
const ROW_Z0 = -7, ROW_DZ = 6.5;

export function createOfficeScene(canvas, container) {
  const W = container.clientWidth || 800, H = container.clientHeight || 600;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(C.bg);

  // 视角: 智能体背后 + 屋顶俯视（参考图），OrbitControls 可拖拽/缩放/平移
  const aspect = W / H, frustum = 20;
  const camera = new THREE.OrthographicCamera(-frustum * aspect, frustum * aspect, frustum, -frustum, 0.1, 300);
  camera.position.set(0, 28, 36);
  camera.lookAt(0, 0, -2);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setSize(W, H);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, -2);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minZoom = 0.5; controls.maxZoom = 3.5;
  controls.maxPolarAngle = Math.PI / 2.15;   // 不许钻到地板下面
  controls.update();

  // 白底光照: 环境光抬高、直射光降低 → 阴影浅而柔（shadow.radius 大半径软化）
  scene.add(new THREE.AmbientLight(0xffffff, 1.45));
  const sun = new THREE.DirectionalLight(0xffffff, 0.85);
  sun.position.set(14, 30, 12);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.radius = 8;
  sun.shadow.bias = -0.0004;
  const sc = sun.shadow.camera; sc.left = -40; sc.right = 40; sc.top = 40; sc.bottom = -40;
  scene.add(sun);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(90, 70),
    new THREE.MeshStandardMaterial({ color: C.floor, roughness: 0.95 })
  );
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true;
  scene.add(floor);

  const props = new THREE.Group(); scene.add(props);
  const agentsGroup = new THREE.Group(); scene.add(agentsGroup);
  const edgesGroup = new THREE.Group(); scene.add(edgesGroup);
  const stageBandsGroup = new THREE.Group(); scene.add(stageBandsGroup);   // M2-5 阶段分区带
  const fxGroup = new THREE.Group(); scene.add(fxGroup);                    // M2-2/M2-3 波纹/脉冲特效
  // XB-6.1 生境轻量层：生态位图腾 + 觅食光点
  const habitatLayer = new THREE.Group(); habitatLayer.name = 'habitatLayer'; scene.add(habitatLayer);
  const forageParticles = []; // {mesh, t, life, vx, vy, vz}
  let workflowMap = {};          // M2-4: "from|to" -> 传递内容
  let workflowOrder = {};        // M2-4: "from|to" -> 递交顺序序号
  let stageBandsKey = '';        // M2-5: 阶段映射签名，避免重复重建
  const ripples = [];            // M2-3: 广播波纹 [{mesh, t, from}]
  const broadcastSeen = new Set();
  const agentBubbles = {};       // agentId → {sprite, canvas, ctx, tex, timer} 气泡
  let raycaster = null;          // 点击拾取
  let mouse = null;

  const furnMat = () => new THREE.MeshStandardMaterial({ color: C.furniture, roughness: 0.9 });
  function box(w, h, d, x, y, z, mat, parent) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat || furnMat());
    m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true;
    (parent || props).add(m); return m;
  }

  // ── 工位: 屏幕朝 -z（Agent 背对摄像机，与参考图一致） ──
  function buildDesk(x, z) {
    const g = new THREE.Group(); g.position.set(x, 0, z);
    box(3.0, 0.16, 1.6, 0, 1.5, 0, null, g);
    [[-1.35, 0.7], [1.35, 0.7], [-1.35, -0.7], [1.35, -0.7]].forEach(([lx, lz]) =>
      box(0.12, 1.5, 0.12, lx, 0.75, lz, null, g));
    box(0.24, 0.5, 0.06, 0, 2.1, -0.45, null, g);
    const screen = box(1.5, 0.9, 0.07, 0, 2.5, -0.45,
      new THREE.MeshStandardMaterial({ color: C.screenOff, emissive: C.screenOff, emissiveIntensity: 0.4 }), g);
    // 办公椅: 座面+靠背+滚轮底座，Agent 坐在座面上
    box(1.0, 0.14, 1.0, 0, 0.9, 1.55, null, g);            // 座面 (顶面 y≈0.97)
    box(1.0, 1.0, 0.12, 0, 1.5, 2.05, null, g);            // 靠背
    box(0.14, 0.9, 0.14, 0, 0.45, 1.55, null, g);          // 支柱
    props.add(g);
    return {
      group: g, screen,
      seat: new THREE.Vector3(x, 0.97, z + 1.55),          // 座面高度 —— 不再坐地上
      aside: new THREE.Vector3(x + 1.6, 0, z + 1.2),
    };
  }

  // ── 白板讨论角（后方中央，面向工位区） ──
  const boardTex = makeBoardTexture([]);
  function buildWhiteboard() {
    const g = new THREE.Group(); g.position.set(0, 0, -13);
    box(0.16, 3.4, 0.16, -2.4, 1.7, 0, null, g);
    box(0.16, 3.4, 0.16, 2.4, 1.7, 0, null, g);
    const board = new THREE.Mesh(
      new THREE.BoxGeometry(5.2, 2.8, 0.1),
      new THREE.MeshStandardMaterial({ map: boardTex.texture, roughness: 0.6 })
    );
    board.position.set(0, 2.3, 0); board.castShadow = true; g.add(board);
    props.add(g);
    return { anchor: new THREE.Vector3(0, 0, -10.8) };
  }
  function makeBoardTexture(lines) {
    const cv = document.createElement('canvas'); cv.width = 512; cv.height = 300;
    const ctx = cv.getContext('2d');
    const texture = new THREE.CanvasTexture(cv);
    function draw(ls) {
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, 512, 300);
      ctx.fillStyle = '#3b4048'; ctx.font = '22px sans-serif';
      ctx.fillText('执 行 计 划', 20, 36);
      ctx.strokeStyle = '#d5d9de'; ctx.beginPath(); ctx.moveTo(20, 48); ctx.lineTo(492, 48); ctx.stroke();
      ctx.font = '17px sans-serif';
      (ls || []).slice(-8).forEach((l, i) => ctx.fillText('· ' + l, 24, 80 + i * 27));
      texture.needsUpdate = true;
    }
    draw(lines);
    return { texture, draw };
  }

  // ── 中央共享区: 咖啡机 / 跑步机 / 马桶 一字排开，左右玻璃护栏 ──
  function buildSharedZone() {
    // 咖啡吧（共享区三件套沿走廊前后均匀分布: -6.5 / +0.5 / +7）
    const bar = new THREE.Group(); bar.position.set(0, 0, -6.5);
    box(3.6, 1.1, 1.3, 0, 0.55, 0, null, bar);
    box(0.7, 0.55, 0.55, 1.0, 1.4, 0, new THREE.MeshStandardMaterial({ color: 0xdddfe3 }), bar);
    for (let i = 0; i < 5; i++) {
      const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.07, 0.16, 10),
        new THREE.MeshStandardMaterial({ color: 0xb07040 }));
      cup.position.set(-1.4 + i * 0.4, 1.2, 0.2); cup.castShadow = true; bar.add(cup);
    }
    props.add(bar);
    // 跑步机: 左右两侧扶手（立柱 + 横杆），不是中间一根
    const tm = new THREE.Group(); tm.position.set(0, 0, 4);
    box(2.4, 0.24, 1.2, 0, 0.14, 0, new THREE.MeshStandardMaterial({ color: 0xe9ebee, roughness: 0.8 }), tm);
    for (const s of [-1, 1]) {
      box(0.1, 1.4, 0.1, -1.05, 0.8, 0.5 * s, null, tm);        // 前立柱
      box(1.6, 0.08, 0.1, -0.35, 1.5, 0.5 * s, null, tm);       // 侧扶手横杆
    }
    box(0.9, 0.5, 0.08, -1.05, 1.35, 0, null, tm);              // 前方仪表板
    props.add(tm);
    // 马桶
    const wc = new THREE.Group(); wc.position.set(0, 0, 14);
    const wcMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.35 });
    box(0.9, 0.5, 1.1, 0, 0.25, 0, wcMat, wc);
    const bowl = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.34, 0.3, 16), wcMat);
    bowl.position.set(0, 0.62, 0.15); bowl.castShadow = true; wc.add(bowl);
    box(0.8, 0.9, 0.22, 0, 0.95, -0.42, wcMat, wc);
    props.add(wc);
    // 玻璃护栏 ×2（半透明，拦出共享走廊）
    const glassMat = new THREE.MeshStandardMaterial({
      color: 0xbfd8e8, transparent: true, opacity: 0.22, roughness: 0.1, side: THREE.DoubleSide,
    });
    for (const s of [-1, 1]) {
      const glass = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.3, 26), glassMat);
      glass.position.set(2.35 * s, 0.75, 4); props.add(glass);
      box(0.1, 0.08, 26, 2.35 * s, 1.45, 4,
        new THREE.MeshStandardMaterial({ color: 0xcfd4da }), props);   // 顶部扶手
    }
    // anchor=使用位, queueDir=排队方向（后到者沿此方向站成一列）
    return {
      coffee: { anchor: new THREE.Vector3(1.3, 0, -5.4), queueDir: new THREE.Vector3(0, 0, 1), y: 0 },
      treadmill: { anchor: new THREE.Vector3(0, 0.3, 4), queueDir: new THREE.Vector3(1.1, 0, 0.6).normalize(), y: 0.3 },
      toilet: { anchor: new THREE.Vector3(0, 0.55, 14.7), queueDir: new THREE.Vector3(0, 0, -1), y: 0.55 },
    };
  }

  // ── Agent 造型: 采用 plaza 的霓虹线框模型（光环头 + U弧身 + 地面光圈 + 名牌） ──
  function buildAgentFigure(def) {
    const g = new THREE.Group();
    // 白底适配: 主体线条加深加实（deep 色 + 高不透明度），辉光收敛避免发灰
    const col = new THREE.Color(def.collar);
    const deep = col.clone().multiplyScalar(0.72);
    const outlineMat = new THREE.MeshBasicMaterial({ color: deep, transparent: true, opacity: 0.95, side: THREE.DoubleSide });
    const glowMat = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.16, side: THREE.DoubleSide });
    // Head ring + glow
    const head = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.035, 12, 32), outlineMat);
    head.position.y = 2.0; g.add(head);
    const headGlow = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.14, 12, 32), glowMat);
    headGlow.position.copy(head.position); g.add(headGlow);
    // Body U-arc
    const pts = [];
    for (let i = 0; i <= 32; i++) {
      const a = Math.PI * (i / 32);
      pts.push(new THREE.Vector3(-Math.cos(a) * 0.48, 1.25 - Math.sin(a) * 0.65, 0));
    }
    const curve = new THREE.CatmullRomCurve3(pts);
    g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 32, 0.035, 8, false), outlineMat));
    g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 32, 0.12, 8, false), glowMat));
    // Ground glow ring
    const glowRing = new THREE.Mesh(
      new THREE.RingGeometry(0.35, 0.55, 32),
      new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.22, side: THREE.DoubleSide })
    );
    glowRing.rotation.x = -Math.PI / 2; glowRing.position.y = 0.01; g.add(glowRing);
    // 手上的文件（递交数据时可见）
    const file = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.05, 0.46),
      new THREE.MeshStandardMaterial({ color: 0xfefefe, roughness: 0.6 }));
    file.position.set(0.5, 1.05, 0.28); file.visible = false; g.add(file);
    g.add(makeLabel(def.name));
    // ND-5.2: 血条（默认隐藏，eco 模式通过 applyState 激活）
    const hb = makeHealthBar();
    g.add(hb.sprite);
    agentsGroup.add(g);
    return { group: g, file, head, glowRing, healthBar: hb };
  }
  function disposeFigure(f) {
    f.group.traverse((node) => {
      if (node.geometry) node.geometry.dispose();
      const mats = Array.isArray(node.material) ? node.material : (node.material ? [node.material] : []);
      mats.forEach((m) => { if (m.map) m.map.dispose(); m.dispose(); });
    });
    agentsGroup.remove(f.group);
  }

  // ── Agent 气泡: 点击智能体弹出自我介绍 ──
  function makeAgentBubble(agentDef) {
    const cv = document.createElement('canvas');
    cv.width = 384; cv.height = 128;
    const tex = new THREE.CanvasTexture(cv);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
    sp.scale.set(4.0, 1.33, 1);
    sp.position.y = 3.0;
    sp.visible = false;
    return { sprite: sp, canvas: cv, tex, visible: false, timer: 0 };
  }

  function showAgentBubble(agentId, def) {
    let b = agentBubbles[agentId];
    const f = figures[agentId];
    if (!f) return;
    if (!b) {
      b = agentBubbles[agentId] = makeAgentBubble(def);
      f.group.add(b.sprite);
    }
    const ctx = b.canvas.getContext('2d');
    ctx.clearRect(0, 0, 384, 128);
    const name = def.name || agentId;
    const role = def.role || '成员';
    const team = def.team || '';
    const skills = (def.skills || []).join('、') || '暂无';
    const lines = [
      `${name} · ${role}`,
      team ? `团队: ${team}` : '',
      `技能: ${skills.length > 20 ? skills.slice(0, 18) + '…' : skills}`,
    ].filter(Boolean);
    ctx.font = '20px sans-serif';
    const h = 16 + lines.length * 28 + 10;
    ctx.fillStyle = 'rgba(255,255,255,0.96)';
    ctx.strokeStyle = '#c8cdd4'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.roundRect(8, 8, 368, h, 14);
    ctx.fill(); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(180, h + 8); ctx.lineTo(200, h + 28); ctx.lineTo(220, h + 8);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = '#2a2e34';
    lines.forEach((l, i) => ctx.fillText(l.length > 24 ? l.slice(0, 22) + '…' : l, 20, 36 + i * 28));
    b.tex.needsUpdate = true;
    b.sprite.visible = true;
    b.visible = true;
    b.timer = 4.0; // 4 秒后消失
  }

  function hideAgentBubble(agentId) {
    const b = agentBubbles[agentId];
    if (b) { b.sprite.visible = false; b.visible = false; }
  }

  // ── 点击拾取: 点击智能体弹出气泡 ──
  function initPicking() {
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();
    let lastClickTime = 0;
    canvas.addEventListener('pointerdown', () => { lastClickTime = Date.now(); });
    canvas.addEventListener('pointerup', (ev) => {
      if (Date.now() - lastClickTime > 300) return; // 拖拽不触发
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      // 检查点击是否命中任何 agent 的 head mesh
      const agentMeshes = [];
      for (const [aid, f] of Object.entries(figures)) {
        f.group.traverse((o) => {
          if (o.isMesh) { o.userData._agentId = aid; agentMeshes.push(o); }
        });
      }
      // 猫也纳入拾取（猫不在 figures 里，是独立对象）
      if (cat && cat.group) {
        cat.group.traverse((o) => {
          if (o.isMesh) { o.userData._isCat = true; agentMeshes.push(o); }
        });
      }
      // 老鼠也纳入拾取
      if (squeak && squeak.group) {
        squeak.group.traverse((o) => {
          if (o.isMesh) { o.userData._isMouse = true; agentMeshes.push(o); }
        });
      }
      const hits = raycaster.intersectObjects(agentMeshes, false);
      if (hits.length > 0) {
        const hit = hits[0].object;
        // 点击猫 → 弹出对话框
        if (hit.userData._isCat) {
          if (!_petsHidden && window.OfficeAPI && window.OfficeAPI.onCatClick) window.OfficeAPI.onCatClick();
          return;
        }
        // 点击老鼠 → 弹出吱吱气泡
        if (hit.userData._isMouse) {
          if (_petsHidden) return;
          showAgentBubble('squeak_mouse', {
            name: '吱吱', role: '寻路研究员', team: 'pet_squad',
            skills: ['Pathfinding', 'Data Analysis', 'Information Gathering', 'Research', 'Route Planning'],
          });
          return;
        }
        const aid = hit.userData._agentId;
        if (aid) {
          const f = figures[aid];
          if (f && f.def) {
            showAgentBubble(aid, f.def);
            // 点击猫特殊处理（agent 模式: pet_squad 里的猫标记）
            if (f.def._isCat) {
              if (window.OfficeAPI && window.OfficeAPI.onCatClick) window.OfficeAPI.onCatClick();
            }
          }
        }
      }
    });
  }
  initPicking();
  // ── ND-5.2: eco 模式血条 Sprite ──
  function makeHealthBar() {
    const cv = document.createElement('canvas');
    cv.width = 128; cv.height = 20;
    const tex = new THREE.CanvasTexture(cv);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: tex, transparent: true, depthTest: false,
    }));
    sp.scale.set(1.8, 0.28, 1);
    sp.position.y = 2.85; // 名牌(2.6)之上，气泡(3.0)之下
    sp.visible = false;   // 默认隐藏，eco 模式才显示
    return { sprite: sp, canvas: cv, tex };
  }
  // 物竞天择 v2 XT-5.3: 意图 → 头顶符号（🍖觅食/🛡避险/💕求偶/💤静息）
  const INTENT_EMOJI = { forage: '🍖', avoid: '🛡', mate: '💕', rest_explore: '💤' };
  function updateHealthBar(hb, health, maxHealth, survivalTicks, alive, intent) {
    const ctx = hb.canvas.getContext('2d');
    ctx.clearRect(0, 0, 128, 20);
    // 背景
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(0, 0, 128, 20);
    if (alive) {
      // 血条
      const ratio = Math.max(0, Math.min(1, health / (maxHealth || 100)));
      const color = ratio > 0.6 ? '#4caf50' : ratio > 0.3 ? '#ff9800' : '#f44336';
      ctx.fillStyle = color;
      ctx.fillRect(16, 2, (128 - 18) * ratio, 10);
      // 意图符号（左侧）
      const emoji = INTENT_EMOJI[intent] || '';
      if (emoji) {
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(emoji, 1, 12);
      }
      // 文字: 血量 + 生存时长
      ctx.font = 'bold 9px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = '#fff';
      ctx.fillText(Math.round(health) + ' / ' + survivalTicks + 't', 70, 18);
    } else {
      // 死亡标记
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = '#f44336';
      ctx.fillText('DEAD ' + survivalTicks + 't', 64, 14);
    }
    hb.tex.needsUpdate = true;
  }

  function makeLabel(text) {
    const cv = document.createElement('canvas'); cv.width = 256; cv.height = 64;
    const ctx = cv.getContext('2d');
    ctx.font = 'bold 30px sans-serif'; ctx.textAlign = 'center';
    ctx.fillStyle = '#2a2e34'; ctx.fillText(String(text).slice(0, 12), 128, 42);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), transparent: true }));
    sp.scale.set(2.6, 0.65, 1); sp.position.y = 2.6;
    return sp;
  }

  // ── M2-4/M2-5: 工作流内容标签 + 业务阶段分区带 ──
  function makeContentLabel(text, color) {
    const cv = document.createElement('canvas'); cv.width = 256; cv.height = 48;
    const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, 256, 48);
    ctx.font = 'bold 20px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = '#' + new THREE.Color(color != null ? color : 0x3b4048).getHexString();
    ctx.fillText(String(text || '').slice(0, 16), 128, 24);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(cv), transparent: true, depthTest: false,
    }));
    sp.scale.set(3, 0.6, 1);
    return sp;
  }
  const STAGE_COLORS = [0x4d9de0, 0x34d399, 0xf59e0b, 0xf472b6, 0xa78bfa, 0x2bb8a8];
  function renderStageBands(stages) {
    const entries = Object.entries(stages || {});
    const key = entries.map(([r, s]) => r + ':' + s).sort().join(',');
    if (key === stageBandsKey) return;      // 幂等：阶段映射不变不重建
    stageBandsKey = key;
    while (stageBandsGroup.children.length) {
      const o = stageBandsGroup.children.pop();
      o.traverse && o.traverse((n) => {
        if (n.geometry) n.geometry.dispose();
        const ms = Array.isArray(n.material) ? n.material : (n.material ? [n.material] : []);
        ms.forEach((m) => { if (m.map) m.map.dispose(); m.dispose(); });
      });
      stageBandsGroup.remove(o);
    }
    if (!entries.length) return;
    const stagesSet = Array.from(new Set(entries.map(([, s]) => Number(s)))).sort((a, b) => a - b);
    stagesSet.forEach((stage, i) => {
      const z = -12 + i * 5.2;
      const band = new THREE.Mesh(
        new THREE.PlaneGeometry(40, 4.6),
        new THREE.MeshBasicMaterial({ color: STAGE_COLORS[i % STAGE_COLORS.length], transparent: true, opacity: 0.06, side: THREE.DoubleSide })
      );
      band.rotation.x = -Math.PI / 2; band.position.set(0, 0.02, z);
      stageBandsGroup.add(band);
      const roomName = (entries.find(([, s]) => Number(s) === stage) || [])[0] || ('阶段' + stage);
      const label = makeContentLabel('阶段' + stage + ' · ' + roomName, STAGE_COLORS[i % STAGE_COLORS.length]);
      label.position.set(-17, 0.8, z);
      stageBandsGroup.add(label);
    });
  }
  function attachFileLabel(f, text) {
    if (f.fileLabel) { f.file.remove(f.fileLabel); f.fileLabel.material.map.dispose(); f.fileLabel.material.dispose(); }
    f.fileLabel = makeContentLabel(text, 0x2b6cb0);
    f.fileLabel.position.set(0, 0.4, 0);
    f.file.add(f.fileLabel);   // 作为 file 子节点，随 file.visible 自动显隐
  }

  // ── M2-3: 广播波纹（communicate target=broadcast）——以发言者为圆心的地面涟漪 ──
  function spawnRipple(pos, color) {
    const mesh = new THREE.Mesh(
      new THREE.RingGeometry(0.4, 0.6, 40),
      new THREE.MeshBasicMaterial({ color: color != null ? color : 0x4d9de0, transparent: true, opacity: 0.6, side: THREE.DoubleSide })
    );
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(pos.x, 0.03, pos.z);
    fxGroup.add(mesh);
    ripples.push({ mesh, t: 0 });
  }

  // ── M2-2: 技能脉冲（execute_skill）——工位上方脉冲技能名 ──
  function triggerSkillPulse(f, skill) {
    if (f.skillPulse) { f.group.remove(f.skillPulse); f.skillPulse.material.map.dispose(); f.skillPulse.material.dispose(); }
    const sp = makeContentLabel('⚡ ' + skill, 0xf59e0b);
    sp.position.set(0, 2.9, 0);
    sp.scale.set(0.1, 0.02, 1);
    f.group.add(sp);
    f.skillPulse = sp;
    f.skillPulseT = 0;
  }


  // ── 装配 ──
  const desks = [];
  const whiteboard = buildWhiteboard();
  const shared = buildSharedZone();
  // Predator/Prey 生态由 PetEcosystem 接管（模型/行为/台词/TTS 全部数据驱动）
  const petEco = new PetEcosystem(scene, makeLabel);
  let cat = null, squeak = null;
  let _petsHidden = false; // UI 可隐藏 吱吱/小虎：冻结生态步进并压制模型显示
  function setPetsVisible(visible) {
    _petsHidden = !visible;
    for (const p of [cat, squeak]) {
      if (p && p.group) p.group.visible = !!visible;
    }
  }
  petEco.init().then(() => {
    cat = petEco.pets['xiaohu_cat'] || null;
    squeak = petEco.pets['squeak_mouse'] || null;
    if (_petsHidden) setPetsVisible(false); // 异步建好后立即应用隐藏状态
  }).catch((e) => console.warn('[office-scene] PetEcosystem init failed', e));

  function deskFor(index) {
    while (desks.length <= index) {
      const i = desks.length, col = i % 6, row = Math.floor(i / 6);
      desks.push(buildDesk(COL_X[col], ROW_Z0 + row * ROW_DZ));
    }
    return desks[index];
  }

  // ── 状态投影 ──
  const figures = {};       // id -> {group, file, glowRing, target, baseY, def, courier}
  const edgeMeshes = new Map();
  const processedEdges = new Set();
  let mirrorOn = false;
  let _catBubbleHold = 0;   // 事件气泡(遇鼠/评分/问答)保持时间戳，期间不被 catNote 解说覆盖
  let _nicheTotem = null;   // XB-6.1 {group, labelMat, lastDemand}
  const _forageSeen = new Set();

  /**
   * 生境 3D 图腾 / 觅食光点：默认关闭。
   * 用户校准：数字办公室没有「觅食」的孪生语义；「当前需求 + skill hex」不可读、未要求出现在 3D。
   * 需求 skill 请看右侧控制台生态位 chips；任务成功用意图/协作线表达即可。
   * 若将来要恢复实验性可视化，设 window.__ECO_HABITAT_3D__ = true。
   */
  function habitat3dEnabled() {
    return !!(typeof window !== 'undefined' && window.__ECO_HABITAT_3D__);
  }

  function ensureNicheTotem() {
    if (_nicheTotem) return _nicheTotem;
    // 仅在显式开启时创建网格，避免默认污染办公室
    if (!habitat3dEnabled()) return null;
    const g = new THREE.Group();
    g.position.set(8.5, 0, -8);
    g.visible = false;
    habitatLayer.add(g);
    _nicheTotem = { group: g, lastDemand: '' };
    return _nicheTotem;
  }

  function updateNicheTotem(env) {
    // 默认永不展示蓝柱黄球「当前需求 xxxx」
    if (_nicheTotem) _nicheTotem.group.visible = false;
    if (!habitat3dEnabled()) return;
    void env;
    void ensureNicheTotem;
  }

  /** 觅食成功光点：默认同关闭（办公室无「觅食」孪生） */
  function spawnForageSpark(agentId) {
    if (!habitat3dEnabled()) return;
    void agentId;
  }

  function targetFor(agent, idxInMeeting, meetingCount, facilities) {
    if (agent.activity === 'meeting') {
      const n = Math.max(meetingCount, 1), a = whiteboard.anchor;
      const ang = -0.7 + (idxInMeeting / Math.max(n - 1, 1)) * 1.4;
      return { pos: new THREE.Vector3(a.x + Math.sin(ang) * 2.6, 0, a.z + Math.cos(ang) * 2.2), y: 0 };
    }
    const fac = shared[agent.activity];
    if (fac) {
      // 设施位: 占用者在使用位；排队者沿 queueDir 站成 FIFO 一列（间距 1.0）
      const fs = facilities && facilities[agent.activity];
      if (fs && fs.occupant === agent.id) return { pos: fac.anchor.clone(), y: fac.y };
      const qi = fs ? fs.queue.indexOf(agent.id) : -1;
      const slot = qi >= 0 ? qi + 1 : 1;
      return {
        pos: fac.anchor.clone().add(fac.queueDir.clone().multiplyScalar(1.0 + slot * 1.0)).setY(0),
        y: 0,
      };
    }
    const d = deskFor(agent.deskIndex);
    if (agent.activity === 'working') return { pos: d.seat.clone().setY(0), y: 0.97 };  // 坐椅面
    return { pos: d.aside.clone(), y: 0 };
  }

  function applyState(state) {
    // M2-4/M2-5: 工作流内容映射 + 业务阶段分区带
    workflowMap = {}; workflowOrder = {};
    (state.workflow || []).forEach((w) => {
      workflowMap[w.from + '|' + w.to] = w.content;
      workflowOrder[w.from + '|' + w.to] = w.order;
    });
    renderStageBands(state.stages || {});
    // 生境 3D 图腾/觅食光点默认关闭（见 updateNicheTotem）
    updateNicheTotem(state.ecoEnv || null);
    if (habitat3dEnabled()) {
      const forageHits = (state.ecoEnv && state.ecoEnv.forage_hits) || [];
      for (let i = 0; i < forageHits.length; i++) {
        const aid = forageHits[i];
        const key = (state.ecoEnv && state.ecoEnv.step != null ? state.ecoEnv.step : 'x') + '|' + aid;
        if (_forageSeen.has(key)) continue;
        _forageSeen.add(key);
        if (_forageSeen.size > 200) {
          _forageSeen.clear();
          _forageSeen.add(key);
        }
        spawnForageSpark(aid);
      }
    }
    const meetingIds = Object.values(state.agents)
      .filter((a) => a.activity === 'meeting').map((a) => a.id);
    for (const agent of Object.values(state.agents)) {
      let f = figures[agent.id];
      if (!f) {
        const built = buildAgentFigure(agent);
        f = figures[agent.id] = {
          group: built.group, file: built.file, glowRing: built.glowRing,
          target: new THREE.Vector3(), baseY: 0, def: agent, courier: null,
        };
        const t = targetFor(agent, 0, 1, state.facilities);
        f.group.position.copy(t.pos); f.baseY = t.y;
      }
      f.def = agent;
      // 物竞天择 v2: 回放中出生的后代 → 小号 figure 落位（长大动画：随生存时长恢复原尺寸）
      if (agent.ecoNewborn && !f._ecoGrown) {
        const grow = Math.min(1, 0.72 + (agent.survivalTicks || 0) / 120);
        f.group.scale.setScalar(grow);
        if (grow >= 1) f._ecoGrown = true;
      }
      // ND-5.2: eco 模式 — 血条显示与更新
      if (agent.health != null && agent.health < 100 || agent.survivalTicks > 0) {
        if (f.healthBar) {
          f.healthBar.sprite.visible = true;
          updateHealthBar(f.healthBar, agent.health, 100, agent.survivalTicks || 0,
            agent.ecoAlive !== false, agent.ecoIntent || '');
        }
      }
      const t = targetFor(agent, Math.max(meetingIds.indexOf(agent.id), 0), meetingIds.length, state.facilities);
      f.target.copy(t.pos); f.baseY = t.y;
      // M2-2: execute_skill → 工位上方技能脉冲（skillUsed 变化时触发）
      if (agent.skillUsed && agent.skillUsed !== f.lastSkill) {
        f.lastSkill = agent.skillUsed;
        triggerSkillPulse(f, agent.skillUsed);
      }
      const desk = deskFor(agent.deskIndex);
      const on = agent.activity === 'working';
      desk.screen.material.color.setHex(on ? C.screenOn : C.screenOff);
      desk.screen.material.emissive.setHex(on ? C.screenOn : C.screenOff);
      desk.screen.material.emissiveIntensity = on ? 0.9 : 0.3;
    }
    // 花名册收窄（团队/成员筛选）→ 移除不在编的 Agent 并释放资源
    for (const id of Object.keys(figures)) {
      if (!state.agents[id]) {
        disposeFigure(figures[id]);
        delete figures[id];
      }
    }
    // 桌子随编制收缩: 拆除多余空桌（幽灵清退后不留一片空工位）
    const neededDesks = Object.values(state.agents)
      .reduce((m, a) => Math.max(m, a.deskIndex + 1), 0);
    while (desks.length > Math.max(neededDesks, 1)) {
      const d = desks.pop();
      props.remove(d.group);
      d.group.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
        const mats = Array.isArray(o.material) ? o.material : (o.material ? [o.material] : []);
        mats.forEach((m) => { if (m.map) m.map.dispose(); m.dispose(); });
      });
    }
    // 新协作边 → 递文件动画任务（Agent 拿文件走到下游工位交接）
    // M2-3: broadcast 边（to='*'）→ 以发言者为圆心的地面波纹（不走递文件）
    for (const e of state.edges) {
      if (e.kind !== 'broadcast') continue;
      const bkey = e.from + '|' + Math.ceil(e.ttl);
      if (broadcastSeen.has(bkey)) continue;
      broadcastSeen.add(bkey);
      setTimeout(() => broadcastSeen.delete(bkey), 4000);
      const fa = figures[e.from];
      if (fa) spawnRipple(fa.group.position, (fa.def && fa.def.collar) || 0x4d9de0);
    }
    for (const e of state.edges) {
      if (e.kind === 'broadcast') continue;
      // v2.4: eco 生境边（信号/求偶/捕食）只画弧线，不触发递文件动画——
      // 否则回放时每个 creature 发信号都会真的走过去"递文件"，全员朝信号目标跑，
      // 看起来像"集体向一个方向跑"（用户 2026-07-11 反馈，根因不是演练数据而是 edge→courier 联动）。
      if (e.kind === 'signal_food' || e.kind === 'signal_help' || e.kind === 'signal_court'
          || e.kind === 'mate' || e.kind === 'predator') continue;
      const key = e.from + '|' + e.to + '|' + Math.ceil(e.ttl);
      const routeKey = e.from + '|' + e.to;
      if (processedEdges.has(routeKey)) continue;
      const fa = figures[e.from], fb = figures[e.to];
      if (fa && fb && !fa.courier) {
        const order = workflowOrder[e.from + '|' + e.to];
        // M2-4 顺序约束: 有更早序号的工作流递交仍在进行 → 本次先等（下游等上游交完）
        if (order != null && _hasEarlierActiveCourier(order)) continue;
        processedEdges.add(routeKey);
        setTimeout(() => processedEdges.delete(routeKey), 8000);   // 同一对 8s 内不重复跑腿
        const content = workflowMap[e.from + '|' + e.to];          // M2-4: 传递内容
        fa.courier = { phase: 'go', toId: e.to, kind: e.kind, content, order };
        fa.file.visible = true;
        if (content) attachFileLabel(fa, content);                 // 文件上显示传递内容标签
      }
      void key;
    }
    // 协作轨迹线（历史热度的空间痕迹）
    const seen = new Set();
    for (const e of state.edges) {
      const key = e.from + '|' + e.to + '|' + e.kind;
      seen.add(key);
      // ND-5.2: 捕食连线 — from=__predator__ 时画从天而降的红色竖线
      if (e.kind === 'predator') {
        const fb = figures[e.to];
        if (!fb) continue;
        let mesh = edgeMeshes.get(key);
        const target = fb.group.position.clone();
        const p0 = target.clone().setY(5.0);  // 从天上
        const p2 = target.clone().setY(2.0);  // 到头顶
        if (!mesh) {
          const geom = new THREE.BufferGeometry().setFromPoints([p0, p2]);
          mesh = new THREE.Line(geom, new THREE.LineBasicMaterial({ color: 0xff3030, transparent: true, opacity: 0.9, linewidth: 3 }));
          // 红色警告环
          const ring = new THREE.Mesh(
            new THREE.RingGeometry(0.3, 0.5, 16),
            new THREE.MeshBasicMaterial({ color: 0xff3030, transparent: true, opacity: 0.6, side: THREE.DoubleSide })
          );
          ring.rotation.x = -Math.PI / 2; ring.position.copy(target).setY(0.02);
          ring.name = 'predatorRing';
          mesh.add(ring);
          edgesGroup.add(mesh); edgeMeshes.set(key, mesh);
        } else {
          mesh.geometry.dispose();
          mesh.geometry = new THREE.BufferGeometry().setFromPoints([p0, p2]);
          const ring = mesh.getObjectByName('predatorRing');
          if (ring) ring.position.copy(target).setY(0.02);
        }
        mesh.material.opacity = Math.max(e.ttl / 3, 0.1) * 0.9;
        continue;
      }
      const fa = figures[e.from], fb = figures[e.to];
      if (!fa || !fb) continue;
      let mesh = edgeMeshes.get(key);
      const p0 = fa.group.position.clone().setY(1.8);
      const p2 = fb.group.position.clone().setY(1.8);
      const mid = p0.clone().add(p2).multiplyScalar(0.5).setY(3.6);
      const curve = new THREE.QuadraticBezierCurve3(p0, mid, p2);
      // 连线配色（v3 高区分度）：协作=冷色系，eco 信号=暖色系，互不混淆
      //   help(青绿) delegate(橙) comm(蓝) ← 协作
      //   food(亮黄) help_signal(红) court/mate(紫红) ← eco 信号
      //   predator(白红竖线，单独处理不在此)
      const edgeColor = e.kind === 'help' ? 0x00e676        // 协作帮助：亮绿
        : e.kind === 'delegate' ? 0xff6d00                   // 委派：亮橙
        : e.kind === 'comm' ? 0x00b0ff                       // 沟通：亮蓝
        : e.kind === 'signal_food' ? 0xffeb3b                // 觅食信号：亮黄
        : e.kind === 'signal_help' ? 0xff1744                // 求助信号：亮红
        : (e.kind === 'signal_court' || e.kind === 'mate') ? 0xd500f9  // 求偶/交配：亮紫
        : 0x4d9de0;                                          // 默认：蓝
      if (!mesh) {
        mesh = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 20, 0.06, 8, false),
          new THREE.MeshBasicMaterial({ color: edgeColor, transparent: true, opacity: 0.85 })
        );
        edgesGroup.add(mesh); edgeMeshes.set(key, mesh);
        if (e.kind === 'delegate') {                       // M2-3: 委派有向箭头
          const cone = new THREE.Mesh(
            new THREE.ConeGeometry(0.16, 0.42, 10),
            new THREE.MeshBasicMaterial({ color: edgeColor, transparent: true, opacity: 0.9 })
          );
          cone.name = 'arrow'; mesh.add(cone);
        }
      } else {
        mesh.geometry.dispose();
        mesh.geometry = new THREE.TubeGeometry(curve, 20, 0.06, 8, false);
      }
      const arrow = mesh.getObjectByName && mesh.getObjectByName('arrow');
      if (arrow) {                                          // 箭头指向下游末端
        const dir = p2.clone().sub(p0).setY(0).normalize();
        arrow.position.copy(p2.clone().addScaledVector(dir, -0.3));
        arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      }
      mesh.material.opacity = Math.max(e.ttl / 6, 0.1) * 0.8;
    }
    for (const [key, mesh] of edgeMeshes) {
      if (!seen.has(key)) {
        edgesGroup.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose();
        edgeMeshes.delete(key);
      }
    }
    boardTex.draw(state.meeting.boardLines);
    // 猫气泡跟随状态（事件气泡保持期内不覆盖）
    if (state.catNote !== applyState._lastCatNote && Date.now() >= _catBubbleHold) {
      applyState._lastCatNote = state.catNote;
      if (cat) cat.drawBubble(state.catNote);
    }
    if (state.mirror !== mirrorOn) {
      mirrorOn = state.mirror;
      // 镜像层视觉: 蓝图幽灵化（半透明 + 蓝调），形状可读，区分度靠色调与徽标
      const tint = new THREE.Color(0x9fb8d8);
      props.traverse((o) => {
        if (!o.isMesh) return;
        const m = o.material;
        if (mirrorOn) {
          o.userData._mirrorBak = {
            color: m.color.getHex(), transparent: m.transparent, opacity: m.opacity,
          };
          m.transparent = true;
          m.opacity = Math.min(m.opacity, 0.42);
          m.color.lerp(tint, 0.5);
        } else if (o.userData._mirrorBak) {
          const b = o.userData._mirrorBak;
          m.color.setHex(b.color);
          m.transparent = b.transparent;
          m.opacity = b.opacity;
          delete o.userData._mirrorBak;
        }
      });
      floor.material.color.setHex(mirrorOn ? 0xeef2f8 : C.floor);
      scene.background.setHex(mirrorOn ? 0xe8edf5 : C.bg);
    }
  }

  // ── 动画循环 ──
  const clock = new THREE.Clock();
  let disposed = false;
  const _v = new THREE.Vector3();

  function stepCourier(f, dt, t) {
    const c = f.courier;
    const to = figures[c.toId];
    if (!to) { f.courier = null; f.file.visible = false; return; }
    if (c.phase === 'go') {
      _v.copy(to.group.position).setY(0);
      _v.add(new THREE.Vector3(1.1, 0, 0.6));                 // 站到对方工位旁
      const cur = f.group.position;
      const dir = _v.clone().sub(cur).setY(0);
      if (dir.length() < 0.25) { c.phase = 'handover'; c.wait = 0.9; return; }
      dir.normalize().multiplyScalar(3.2 * dt);
      cur.add(dir);
      cur.y = Math.abs(Math.sin(t * 10)) * 0.08;              // 走路颠簸
      f.group.lookAt(_v.x, cur.y, _v.z);
      return;
    }
    if (c.phase === 'handover') {
      c.wait -= dt;
      if (c.wait <= 0) {
        f.file.visible = false;
        to.file.visible = true;                               // 文件交到对方手上
        setTimeout(() => { to.file.visible = false; }, 1500); // 对方收好文件
        c.phase = 'return';
      }
      return;
    }
    // return: 回自己的位置
    const back = f.target;
    const cur = f.group.position;
    const dir = back.clone().sub(cur).setY(0);
    if (dir.length() < 0.3) { f.courier = null; return; }
    dir.normalize().multiplyScalar(3.2 * dt);
    cur.add(dir); cur.y = 0;
    f.group.lookAt(back.x, 0, back.z);
  }

  function nearestCatLure() {
    if (!cat) return null;
    let nearest = null;
    let best = Infinity;
    for (const f of Object.values(figures)) {
      if (f.courier) continue;
      const dx = f.group.position.x - cat.group.position.x;
      const dz = f.group.position.z - cat.group.position.z;
      const d2 = dx * dx + dz * dz;
      if (d2 < best) { best = d2; nearest = f; }
    }
    return nearest;
  }

  // M2-4: 是否有更早序号的工作流递交仍在进行（顺序约束用）
  function _hasEarlierActiveCourier(order) {
    for (const f of Object.values(figures)) {
      if (f.courier && f.courier.order != null && f.courier.order < order) return true;
    }
    return false;
  }

  // M2-2/M2-3: 波纹扩散 + 技能脉冲动画（每帧推进，结束即释放）
  function _stepFx(dt) {
    for (let i = ripples.length - 1; i >= 0; i--) {
      const r = ripples[i];
      r.t += dt;
      const s = 1 + r.t * 6;
      r.mesh.scale.set(s, s, s);
      r.mesh.material.opacity = Math.max(0, 0.6 - r.t * 0.5);
      if (r.mesh.material.opacity <= 0.01) {
        fxGroup.remove(r.mesh); r.mesh.geometry.dispose(); r.mesh.material.dispose();
        ripples.splice(i, 1);
      }
    }
    for (const f of Object.values(figures)) {
      if (!f.skillPulse) continue;
      f.skillPulseT += dt;
      const p = f.skillPulseT;
      if (p < 0.25) {                                   // 弹出
        const k = p / 0.25;
        f.skillPulse.scale.set(2.4 * k, 0.5 * k, 1);
      } else if (p < 1.4) {                             // 停留
        f.skillPulse.scale.set(2.4, 0.5, 1);
        f.skillPulse.material.opacity = 1;
      } else if (p < 1.9) {                             // 淡出
        f.skillPulse.material.opacity = Math.max(0, 1 - (p - 1.4) / 0.5);
      } else {
        f.group.remove(f.skillPulse);
        f.skillPulse.material.map.dispose(); f.skillPulse.material.dispose();
        f.skillPulse = null;
      }
    }
  }

  function animate() {
    if (disposed) return;
    requestAnimationFrame(animate);
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.getElapsedTime();
    const catLure = nearestCatLure();
    for (const f of Object.values(figures)) {
      if (f.courier) { stepCourier(f, dt, t); continue; }
      // 常规: 平滑走向目标 + 落座高度 + 轻微呼吸/跑步颠簸
      const act = f.def.activity;
      let bob = Math.sin(t * 2 + f.def.deskIndex) * 0.03;
      if (act === 'treadmill') bob = Math.abs(Math.sin(t * 8)) * 0.18;
      if (act === 'meeting' && f.def.id === (window.OfficeAPI && window.OfficeAPI._speakerId)) {
        bob = Math.abs(Math.sin(t * 6)) * 0.12;
      }
      _v.copy(f.target).setY(f.baseY + bob);
      f.group.position.lerp(_v, 0.06);
      if (act === 'working') f.group.lookAt(f.group.position.x, f.group.position.y, f.group.position.z - 4); // 面朝屏幕(-z)
      if (f === catLure) {
        f.group.lookAt(cat.group.position.x, f.group.position.y, cat.group.position.z);
        if (f.glowRing) {
          const pulse = (Math.sin(t * 7) + 1) / 2;
          f.glowRing.material.opacity = 0.24 + pulse * 0.42;
          const ringScale = 1 + pulse * 0.38;
          f.glowRing.scale.set(ringScale, ringScale, ringScale);
        }
      } else if (f.glowRing) {
        f.glowRing.material.opacity = 0.22;
        f.glowRing.scale.set(1, 1, 1);
      }
      // ND-5.2: 死亡淡出 — ecoAlive=false 时逐渐降低不透明度（血条 Sprite 除外）
      if (f.def.ecoAlive === false && !f._ecoDeadFaded) {
        f.group.traverse(function(node) {
          if (node.material && node !== (f.healthBar && f.healthBar.sprite)) {
            var mats = Array.isArray(node.material) ? node.material : [node.material];
            mats.forEach(function(m) {
              if (!m._ecoOrigOpacity) m._ecoOrigOpacity = m.opacity;
              m.transparent = true;
              m.opacity = Math.max(0.12, m.opacity * 0.96);
            });
          }
        });
        f._ecoWasDead = true;
        if (f.group.children[0] && f.group.children[0].material && f.group.children[0].material.opacity < 0.15) {
          f._ecoDeadFaded = true;
        }
      }
      // v2.3: 复活/重跑恢复 — eco_reset 把 ecoAlive 置回 true 后，恢复原始不透明度
      // （否则重跑物竞天择时上一场死者仍是幽灵，看起来"3D 没有 Agent 动画了"）
      if (f.def.ecoAlive !== false && (f._ecoDeadFaded || f._ecoWasDead)) {
        f.group.traverse(function(node) {
          if (node.material) {
            var mats = Array.isArray(node.material) ? node.material : [node.material];
            mats.forEach(function(m) {
              if (m._ecoOrigOpacity != null) m.opacity = m._ecoOrigOpacity;
            });
          }
        });
        f._ecoDeadFaded = false;
        f._ecoWasDead = false;
      }
    }
    // Predator/Prey 生态：小虎(捕食者) + 吱吱(猎物) 的模型/行为/台词全部由 PetEcosystem 驱动
    if (_petsHidden) {
      // 已隐藏：冻结生态步进（不再移动/冒泡/说话），并压制后建模型的显示
      if (cat && cat.group) cat.group.visible = false;
      if (squeak && squeak.group) squeak.group.visible = false;
    } else {
      petEco.step(dt, t);
    }
    _stepFx(dt);
    // XB-6.1 觅食光点飞行
    for (let i = forageParticles.length - 1; i >= 0; i--) {
      const p = forageParticles[i];
      p.t += dt;
      const u = Math.min(1, p.t / p.life);
      // ease-out 抛物线
      const yBoost = Math.sin(u * Math.PI) * 1.2;
      p.mesh.position.lerpVectors(p.from, p.to, u);
      p.mesh.position.y += yBoost;
      p.mesh.material.opacity = 0.95 * (1 - u);
      p.mesh.scale.setScalar(1 + u * 0.6);
      if (u >= 1) {
        habitatLayer.remove(p.mesh);
        p.mesh.geometry.dispose();
        p.mesh.material.dispose();
        forageParticles.splice(i, 1);
      }
    }
    // 图腾光球缓动
    if (_nicheTotem && _nicheTotem.group.visible) {
      const orb = _nicheTotem.group.getObjectByName('nicheOrb');
      if (orb) {
        orb.position.y = 2.35 + Math.sin(t * 2.4) * 0.08;
        orb.scale.setScalar(1 + Math.sin(t * 3.1) * 0.06);
      }
    }
    // Agent 气泡倒计时
    for (const [aid, b] of Object.entries(agentBubbles)) {
      if (b.visible) {
        b.timer -= dt;
        if (b.timer <= 0) hideAgentBubble(aid);
      }
    }
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  const resizeObs = new ResizeObserver(() => {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    const asp = w / h;
    camera.left = -frustum * asp; camera.right = frustum * asp;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  });
  resizeObs.observe(container);

  return {
    applyState,
    showAgentBubble,
    setPetsVisible,
    showCatBubble(text) {
      _catBubbleHold = Date.now() + 10000;
      if (cat) cat.drawBubble(text);
    },
    onRewardUpdate(reward, prevReward) {
      // 评分波动评价已注释掉 — 避免与 LLM 台词 TTS 冲突
      // if (typeof reward !== 'number' || typeof prevReward !== 'number') return;
      // const delta = reward - prevReward;
      // const absDelta = Math.abs(delta);
      // if (absDelta < 0.05) return;
      // let comment = '';
      // if (delta > 0.15) {
      //   const praise = ['喵~ 这步表现不错嘛，看来大家配合得挺好！', '呼噜~ 分数涨了，干得漂亮！', '喵呜~ 这个协作效率我喜欢！'];
      //   comment = praise[Math.floor(Math.random() * praise.length)];
      // } else if (delta > 0.05) {
      //   comment = '喵~ 有进步，继续保持哦~';
      // } else if (delta < -0.15) {
      //   const worry = ['喵...这步怎么退步了？是不是有人偷懒了？', '嘶~ 分数掉了不少，得注意一下协作质量啊！', '喵呜...这个方向不太对，要不要换个思路？'];
      //   comment = worry[Math.floor(Math.random() * worry.length)];
      // } else if (delta < -0.05) {
      //   comment = '喵...分数有点波动，稳一稳吧~';
      // }
      // if (comment) {
      //   _catBubbleHold = Date.now() + 8000;
      //   if (cat) cat.drawBubble('🐈 ' + comment);
      //   if (window.OfficeAPI && window.OfficeAPI.onCatComment) window.OfficeAPI.onCatComment(comment);
      // }
    },
    dispose() {
      disposed = true; resizeObs.disconnect(); controls.dispose();
      renderer.dispose();
    },
  };
}
