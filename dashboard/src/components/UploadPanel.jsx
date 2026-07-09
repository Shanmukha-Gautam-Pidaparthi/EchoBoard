import { useState } from "react";
import { api } from "../api";

export default function UploadPanel({ onDone }) {
  const [mode, setMode] = useState("video");
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  // video params
  const [sampleN, setSampleN] = useState(3);
  const [motionT, setMotionT] = useState(0.03);
  const [stableN, setStableN] = useState(4);
  const [contentT, setContentT] = useState(0.05);
  const [url, setUrl] = useState("");

  async function handleVideoUpload(e) {
    e.preventDefault();
    const file = e.target.elements.videoFile.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("sample_every_n_frames", sampleN);
    fd.append("motion_threshold", motionT);
    fd.append("stable_frames_required", stableN);
    fd.append("new_content_threshold", contentT);
    setLoading(true); setStatus(null);
    try {
      const res = await api.uploadVideo(fd);
      setStatus({ ok: true, msg: `✅ ${res.keyframes_captured} keyframes captured from "${res.filename}"` });
      onDone();
    } catch { setStatus({ ok: false, msg: "Upload failed." }); }
    setLoading(false);
  }

  async function handleImagesUpload(e) {
    e.preventDefault();
    const files = e.target.elements.imgFiles.files;
    if (!files.length) return;
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    setLoading(true); setStatus(null);
    try {
      const res = await api.uploadImages(fd);
      setStatus({ ok: true, msg: `✅ ${res.images_stored} images stored.` });
      onDone();
    } catch { setStatus({ ok: false, msg: "Upload failed." }); }
    setLoading(false);
  }

  async function handleUrlUpload(e) {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true); setStatus(null);
    try {
      const res = await api.uploadUrl({
        url, sample_every_n_frames: sampleN,
        motion_threshold: motionT, stable_frames_required: stableN,
        new_content_threshold: contentT,
      });
      setStatus({ ok: true, msg: `✅ "${res.title}" is downloading & processing in the background!` });
      setTimeout(() => {
        onDone();
      }, 1000);
    } catch {
      setStatus({ ok: false, msg: "Processing failed." });
      setLoading(false);
    }
  }

  return (
    <div style={styles.wrap}>
      <div style={styles.tabs}>
        {["video", "images", "url"].map(m => (
          <button key={m} onClick={() => setMode(m)}
            style={{ ...styles.tab, ...(mode === m ? styles.activeTab : {}) }}>
            {m === "video" ? "📹 Video" : m === "images" ? "🖼️ Images" : "🔗 URL"}
          </button>
        ))}
      </div>

      {mode === "video" && (
        <form onSubmit={handleVideoUpload} style={styles.form}>
          <input name="videoFile" type="file" accept=".mp4,.avi,.mov,.mkv,.webm" style={styles.input} />
          <ParamSliders {...{ sampleN, setSampleN, motionT, setMotionT, stableN, setStableN, contentT, setContentT }} />
          <button type="submit" style={styles.btn} disabled={loading}>{loading ? "Processing…" : "Process Video"}</button>
        </form>
      )}

      {mode === "images" && (
        <form onSubmit={handleImagesUpload} style={styles.form}>
          <input name="imgFiles" type="file" accept=".jpg,.jpeg,.png,.bmp,.webp" multiple style={styles.input} />
          <button type="submit" style={styles.btn} disabled={loading}>{loading ? "Storing…" : "Store Images"}</button>
        </form>
      )}

      {mode === "url" && (
        <form onSubmit={handleUrlUpload} style={styles.form}>
          <input value={url} onChange={e => setUrl(e.target.value)}
            placeholder="https://youtube.com/watch?v=…" style={styles.input} />
          <ParamSliders {...{ sampleN, setSampleN, motionT, setMotionT, stableN, setStableN, contentT, setContentT }} />
          <button type="submit" style={styles.btn} disabled={loading}>{loading ? "Downloading…" : "Download & Process"}</button>
        </form>
      )}

      {status && (
        <p style={{ color: status.ok ? "#4ade80" : "#f87171", marginTop: 12 }}>{status.msg}</p>
      )}
    </div>
  );
}

function ParamSliders({ sampleN, setSampleN, motionT, setMotionT, stableN, setStableN, contentT, setContentT }) {
  return (
    <div style={styles.sliders}>
      <Slider label={`Sample every ${sampleN} frames`} min={1} max={10} value={sampleN} onChange={setSampleN} />
      <Slider label={`Motion threshold ${motionT}`} min={0.01} max={2} step={0.01} value={motionT} onChange={setMotionT} />
      <Slider label={`Stable frames ${stableN}`} min={2} max={10} value={stableN} onChange={setStableN} />
      <Slider label={`New content threshold ${contentT}`} min={0.01} max={2} step={0.01} value={contentT} onChange={setContentT} />
    </div>
  );
}

function Slider({ label, min, max, step = 1, value, onChange }) {
  return (
    <label style={styles.sliderLabel}>
      <span style={{ fontSize: 12, color: "#94a3b8" }}>{label}</span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(step < 1 ? parseFloat(e.target.value) : parseInt(e.target.value))}
        style={{ width: "100%" }} />
    </label>
  );
}

const styles = {
  wrap: { background: "#1e293b", borderRadius: 12, padding: 24 },
  tabs: { display: "flex", gap: 8, marginBottom: 20 },
  tab: { padding: "8px 18px", borderRadius: 8, border: "none", background: "#334155", color: "#94a3b8", cursor: "pointer" },
  activeTab: { background: "#0ea5e9", color: "#fff" },
  form: { display: "flex", flexDirection: "column", gap: 14 },
  input: { padding: 10, borderRadius: 8, border: "1px solid #334155", background: "#0f172a", color: "#e2e8f0", fontSize: 14 },
  sliders: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 },
  sliderLabel: { display: "flex", flexDirection: "column", gap: 4 },
  btn: { padding: "10px 0", borderRadius: 8, border: "none", background: "#0ea5e9", color: "#fff", fontWeight: 600, fontSize: 15, cursor: "pointer" },
};
