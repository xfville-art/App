/**
 * ViraCut Studio — Firebase Cloud Functions
 * Relaie les appels GitHub API avec le token secret côté serveur
 * Deploy: firebase deploy --only functions
 *
 * Variables d'environnement à configurer :
 *   firebase functions:config:set github.token="ghp_VOTRE_TOKEN_ICI"
 */

const functions = require("firebase-functions");
const admin = require("firebase-admin");
const fetch = require("node-fetch");

admin.initializeApp();

const GITHUB_TOKEN = process.env.GITHUB_TOKEN_VIRACUT;
const REPO         = "xfville-art/App";
const BRANCH       = "main";

// ─── Helper : vérifie le token Firebase de l'user ───────────────────────────
async function verifyUser(req, res) {
  const auth = req.headers.authorization || "";
  const idToken = auth.startsWith("Bearer ") ? auth.slice(7) : null;
  if (!idToken) { res.status(401).json({ error: "Non authentifié" }); return null; }
  try {
    const decoded = await admin.auth().verifyIdToken(idToken);
    return decoded;
  } catch (e) {
    res.status(401).json({ error: "Token invalide" });
    return null;
  }
}

// ─── Helper : proxy GitHub ───────────────────────────────────────────────────
async function ghFetch(path, options = {}) {
  const url = `https://api.github.com${path}`;
  const headers = {
    "Authorization": `Bearer ${GITHUB_TOKEN}`,
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  return fetch(url, { ...options, headers });
}

// ─── CORS helper ─────────────────────────────────────────────────────────────
function cors(req, res, next) {
  res.set("Access-Control-Allow-Origin", "*");
  res.set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
  res.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
  if (req.method === "OPTIONS") { res.status(204).send(""); return; }
  next();
}


// ════════════════════════════════════════════════════════════════════════════
// 1. uploadAndDispatch — upload p.json + dispatch viracut.yml
// ════════════════════════════════════════════════════════════════════════════
exports.uploadAndDispatch = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;

    const { payload, wfFile = "viracut.yml" } = req.body;
    if (!payload) { res.status(400).json({ error: "payload manquant" }); return; }

    // 1. Récupère SHA si p.json existe déjà
    let sha = "";
    try {
      const r = await ghFetch(`/repos/${REPO}/contents/p.json`);
      if (r.ok) { const j = await r.json(); sha = j.sha || ""; }
    } catch (_) {}

    // 2. Upload p.json
    const body = { message: "vid", content: btoa(unescape(encodeURIComponent(payload))) };
    if (sha) body.sha = sha;
    const put = await ghFetch(`/repos/${REPO}/contents/p.json`, {
      method: "PUT", body: JSON.stringify(body),
    });
    if (!put.ok) {
      const err = await put.json().catch(() => ({}));
      res.status(500).json({ error: err.message || "Upload échoué" });
      return;
    }

    // 3. Dispatch workflow
    await ghFetch(`/repos/${REPO}/actions/workflows/${wfFile}/dispatches`, {
      method: "POST", body: JSON.stringify({ ref: BRANCH }),
    });

    const dispatchTime = new Date().toISOString();

    // 4. Sauvegarde run en Firestore pour cet user
    await admin.firestore().collection("users").doc(user.uid)
      .collection("runs").add({
        dispatchTime,
        wfFile,
        status: "queued",
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
      });

    res.json({ ok: true, dispatchTime });
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 2. uploadAnalyze — upload pa.json + dispatch viracut_analyze.yml
// ════════════════════════════════════════════════════════════════════════════
exports.uploadAnalyze = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;

    const { payload } = req.body;
    if (!payload) { res.status(400).json({ error: "payload manquant" }); return; }

    let sha = "";
    try {
      const r = await ghFetch(`/repos/${REPO}/contents/pa.json`);
      if (r.ok) { const j = await r.json(); sha = j.sha || ""; }
    } catch (_) {}

    const body = { message: "viralite-analyze", content: btoa(unescape(encodeURIComponent(payload))) };
    if (sha) body.sha = sha;
    const put = await ghFetch(`/repos/${REPO}/contents/pa.json`, {
      method: "PUT", body: JSON.stringify(body),
    });
    if (!put.ok) {
      const err = await put.json().catch(() => ({}));
      res.status(500).json({ error: err.message || "Upload pa.json échoué" });
      return;
    }

    // Dispatch
    await ghFetch(`/repos/${REPO}/actions/workflows/viracut_analyze.yml/dispatches`, {
      method: "POST", body: JSON.stringify({ ref: BRANCH }),
    });

    res.json({ ok: true, dispatchTime: new Date().toISOString() });
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 3. getRuns — liste les runs GitHub Actions
// ════════════════════════════════════════════════════════════════════════════
exports.getRuns = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const perPage = req.query.per_page || 20;
    const r = await ghFetch(`/repos/${REPO}/actions/runs?per_page=${perPage}`);
    const j = await r.json();
    res.json(j);
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 4. getWorkflowRuns — runs d'un workflow précis
// ════════════════════════════════════════════════════════════════════════════
exports.getWorkflowRuns = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const { wf, per_page = 10 } = req.query;
    if (!wf) { res.status(400).json({ error: "wf manquant" }); return; }
    const r = await ghFetch(`/repos/${REPO}/actions/workflows/${wf}/runs?per_page=${per_page}`);
    res.json(await r.json());
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 5. getArtifacts — artifacts d'un run
// ════════════════════════════════════════════════════════════════════════════
exports.getArtifacts = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const { runId } = req.query;
    if (!runId) { res.status(400).json({ error: "runId manquant" }); return; }
    const r = await ghFetch(`/repos/${REPO}/actions/runs/${runId}/artifacts`);
    res.json(await r.json());
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 6. downloadArtifact — redirige vers le zip de l'artifact
// ════════════════════════════════════════════════════════════════════════════
exports.downloadArtifact = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const { artifactId } = req.query;
    if (!artifactId) { res.status(400).json({ error: "artifactId manquant" }); return; }
    const r = await ghFetch(`/repos/${REPO}/actions/artifacts/${artifactId}/zip`, { redirect: "manual" });
    const location = r.headers.get("location");
    if (location) { res.redirect(location); }
    else { res.status(r.status).json({ error: "Redirection introuvable" }); }
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 7. getJobLogs — logs d'un job
// ════════════════════════════════════════════════════════════════════════════
exports.getJobLogs = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const { jobId } = req.query;
    if (!jobId) { res.status(400).json({ error: "jobId manquant" }); return; }
    // Logs redirigent vers une URL signée
    const r = await ghFetch(`/repos/${REPO}/actions/jobs/${jobId}/logs`, { redirect: "follow" });
    const text = await r.text();
    res.send(text);
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 8. getRunJobs — jobs d'un run
// ════════════════════════════════════════════════════════════════════════════
exports.getRunJobs = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const { runId } = req.query;
    if (!runId) { res.status(400).json({ error: "runId manquant" }); return; }
    const r = await ghFetch(`/repos/${REPO}/actions/runs/${runId}/jobs`);
    res.json(await r.json());
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 9. deleteRun — supprime un run GitHub Actions
// ════════════════════════════════════════════════════════════════════════════
exports.deleteRun = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const { runId } = req.query;
    if (!runId) { res.status(400).json({ error: "runId manquant" }); return; }
    const r = await ghFetch(`/repos/${REPO}/actions/runs/${runId}`, { method: "DELETE" });
    res.status(r.status).json({ ok: r.status === 204 });
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 10. saveUserHistory — sauvegarde/met à jour un run dans Firestore
// ════════════════════════════════════════════════════════════════════════════
exports.saveUserHistory = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const { runId, runNumber, status, conclusion, duration, mode, viralScore } = req.body;
    const ref = admin.firestore().collection("users").doc(user.uid)
      .collection("runs").doc(String(runId));
    await ref.set({
      runId, runNumber, status, conclusion, duration, mode,
      viralScore: viralScore || null,
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    }, { merge: true });
    res.json({ ok: true });
  });
});


// ════════════════════════════════════════════════════════════════════════════
// 11. getUserHistory — récupère l'historique Firestore de l'user
// ════════════════════════════════════════════════════════════════════════════
exports.getUserHistory = functions.https.onRequest(async (req, res) => {
  cors(req, res, async () => {
    const user = await verifyUser(req, res);
    if (!user) return;
    const snap = await admin.firestore().collection("users").doc(user.uid)
      .collection("runs").orderBy("updatedAt", "desc").limit(50).get();
    const runs = snap.docs.map(d => ({ id: d.id, ...d.data() }));
    res.json({ runs });
  });
});
