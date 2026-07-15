import { useState } from "react";
import { api } from "./api";
import StatsBar from "./components/StatsBar";
import UploadPanel from "./components/UploadPanel";
import Library from "./components/Library";
import DatasetExplorer from "./components/DatasetExplorer";

const TABS = ["Folder Upload", "Dataset Library", "Dataset Explorer"];

export default function App() {
  const [tab, setTab] = useState("Folder Upload");
  const [refreshKey, setRefreshKey] = useState(0);

  function onUploadDone() {
    setRefreshKey(k => k + 1);
    setTab("Dataset Library");
  }

  return (
    <div style={styles.root}>
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.logo}>📝 EchoBoard</span>
          <span style={styles.badge}>ECHD</span>
        </div>
        <span style={styles.sub}>Dataset Creation Module — Every Lesson Preserved</span>
      </header>

      <main style={styles.main}>
        <StatsBar key={refreshKey} />



        {/* Tab Navigation */}
        <div style={styles.tabs}>
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ ...styles.tab, ...(tab === t ? styles.activeTab : {}) }}>
              {t === "Folder Upload" && "📁 "}
              {t === "Dataset Library" && "📚 "}
              {t === "Dataset Explorer" && "🔬 "}
              {t}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div style={styles.content}>
          {tab === "Folder Upload" && <UploadPanel onDone={onUploadDone} />}
          {tab === "Dataset Library" && <Library refreshKey={refreshKey} />}
          {tab === "Dataset Explorer" && <DatasetExplorer refreshKey={refreshKey} />}
        </div>
      </main>

      <footer style={styles.footer}>
        <span>EchoBoard Classroom Handwriting Dataset (ECHD) — Dataset Creation Module</span>
        <span style={styles.footerSub}>No OCR · No Recognition · No Inference — Raw Dataset Only</span>
      </footer>
    </div>
  );
}

const styles = {
  root: {
    minHeight: "100vh",
    background: "linear-gradient(180deg, #0f172a 0%, #020617 100%)",
    color: "#e2e8f0",
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    padding: "18px 32px",
    borderBottom: "1px solid #1e293b",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "rgba(15, 23, 42, 0.8)",
    backdropFilter: "blur(12px)",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 10 },
  logo: { fontSize: 22, fontWeight: 700, color: "#38bdf8" },
  badge: {
    background: "linear-gradient(135deg, #0ea5e9, #06b6d4)",
    color: "#fff",
    fontSize: 10,
    fontWeight: 700,
    padding: "3px 8px",
    borderRadius: 4,
    letterSpacing: "1px",
  },
  sub: { fontSize: 13, color: "#64748b" },
  main: { maxWidth: 1200, width: "100%", margin: "0 auto", padding: "28px 24px", flex: 1 },
  tabs: { display: "flex", gap: 8, marginBottom: 24 },
  tab: {
    padding: "10px 22px",
    borderRadius: 10,
    border: "1px solid #1e293b",
    background: "#0f172a",
    color: "#94a3b8",
    cursor: "pointer",
    fontSize: 13.5,
    fontWeight: 500,
    transition: "all 0.2s",
  },
  activeTab: {
    background: "linear-gradient(135deg, #0ea5e9, #06b6d4)",
    color: "#fff",
    fontWeight: 600,
    borderColor: "#0ea5e9",
  },
  content: {},
  banner: {
    background: "rgba(14, 165, 233, 0.1)",
    border: "1px solid rgba(14, 165, 233, 0.3)",
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
  footer: {
    borderTop: "1px solid #1e293b",
    padding: "14px 32px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: 12,
    color: "#475569",
  },
  footerSub: { fontStyle: "italic", color: "#334155" },
};
