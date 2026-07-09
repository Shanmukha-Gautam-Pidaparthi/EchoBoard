import { useState, useEffect } from "react";
import { api } from "./api";
import StatsBar from "./components/StatsBar";
import UploadPanel from "./components/UploadPanel";
import Library from "./components/Library";

const TABS = ["Upload", "Library"];

export default function App() {
  const [tab, setTab] = useState("Library");
  const [refreshKey, setRefreshKey] = useState(0);
  const [processingVideos, setProcessingVideos] = useState([]);

  // Periodically check if any videos are still processing
  useEffect(() => {
    function checkProcessing() {
      api.getVideos().then(vs => {
        const active = vs.filter(v => v.processing);
        setProcessingVideos(active);
      }).catch(() => {});
    }

    checkProcessing();
    const interval = setInterval(checkProcessing, 4000);
    return () => clearInterval(interval);
  }, [refreshKey]);

  async function handleStop(id) {
    try {
      await api.stopVideo(id);
      setRefreshKey(k => k + 1);
    } catch (err) {
      console.error(err);
    }
  }

  function onUploadDone() {
    setRefreshKey(k => k + 1);
    setTab("Library");
  }

  return (
    <div style={styles.root}>
      <header style={styles.header}>
        <span style={styles.logo}>📝 EchoBoard</span>
        <span style={styles.sub}>Every Lesson Preserved. Every Concept Searchable.</span>
      </header>

      <main style={styles.main}>
        <StatsBar key={refreshKey} />

        {/* Persistent Background Processing Banners */}
        {processingVideos.map(v => (
          <div key={v.id} style={styles.banner}>
            <span>⏳ Processing in background: <strong>{v.filename}</strong></span>
            <button onClick={() => handleStop(v.id)} style={styles.stopBtn}>Stop Processing</button>
          </div>
        ))}

        <div style={styles.tabs}>
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ ...styles.tab, ...(tab === t ? styles.activeTab : {}) }}>
              {t}
            </button>
          ))}
        </div>

        <div style={styles.content}>
          {tab === "Upload" && <UploadPanel onDone={onUploadDone} />}
          {tab === "Library" && <Library refreshKey={refreshKey} />}
        </div>
      </main>
    </div>
  );
}

const styles = {
  root: { minHeight: "100vh", background: "#0f172a", color: "#e2e8f0", fontFamily: "system-ui, sans-serif" },
  header: { padding: "20px 32px", borderBottom: "1px solid #1e293b", display: "flex", alignItems: "baseline", gap: 12 },
  logo: { fontSize: 22, fontWeight: 700, color: "#38bdf8" },
  sub: { fontSize: 13, color: "#64748b" },
  main: { maxWidth: 1100, margin: "0 auto", padding: "28px 24px" },
  tabs: { display: "flex", gap: 8, marginBottom: 24 },
  tab: { padding: "9px 22px", borderRadius: 8, border: "none", background: "#1e293b", color: "#94a3b8", cursor: "pointer", fontSize: 14 },
  activeTab: { background: "#0ea5e9", color: "#fff", fontWeight: 600 },
  content: {},
  banner: {
    background: "rgba(14, 165, 233, 0.12)",
    border: "1px solid #0ea5e9",
    borderRadius: 10,
    padding: "12px 18px",
    marginBottom: 20,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: 13.5,
    color: "#38bdf8",
  },
  stopBtn: {
    background: "#ef4444",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    padding: "6px 14px",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
  },
};
