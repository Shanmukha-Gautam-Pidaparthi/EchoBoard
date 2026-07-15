import { useState, useRef } from "react";
import { api } from "../api";

const CLASSES = ["Text", "Equation", "Heading", "Diagram", "Table", "Other"];

export default function UploadPanel({ onDone }) {
  const [folderName, setFolderName] = useState("Lecture_01");
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [annotations, setAnnotations] = useState({});
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null);
  const [progress, setProgress] = useState(0);
  const fileInputRef = useRef(null);

  function handleFolderSelect(e) {
    const files = Array.from(e.target.files).filter((f) =>
      f.type.startsWith("image/")
    );
    if (!files.length) {
      setStatus({ ok: false, msg: "No valid images found in selected folder." });
      return;
    }
    setSelectedFiles(files);
    setStatus(null);
    // Initialize empty annotations for each file
    const annMap = {};
    files.forEach((f) => {
      annMap[f.name] = { text: "", class: "Text" };
    });
    setAnnotations(annMap);
  }

  function updateAnnotation(filename, field, value) {
    setAnnotations((prev) => ({
      ...prev,
      [filename]: { ...prev[filename], [field]: value },
    }));
  }

  async function handleUpload(e) {
    e.preventDefault();
    if (!selectedFiles.length) return;

    const fd = new FormData();
    selectedFiles.forEach((f) => fd.append("files", f));
    fd.append("folder_name", folderName);
    fd.append("annotations_json", JSON.stringify(annotations));

    setLoading(true);
    setStatus(null);
    setProgress(0);

    try {
      const res = await api.uploadImages(fd);
      setStatus({
        ok: true,
        msg: `✅ ${res.images_stored} images uploaded to MinIO & MongoDB → folder "${res.folder_name}"`,
      });
      setSelectedFiles([]);
      setAnnotations({});
      if (fileInputRef.current) fileInputRef.current.value = "";
      onDone();
    } catch {
      setStatus({ ok: false, msg: "Upload failed. Check backend logs." });
    }
    setLoading(false);
  }

  return (
    <div style={styles.wrap}>
      {/* Folder Name */}
      <div style={styles.metaSection}>
        <h4 style={styles.sectionTitle}>📁 Dataset Upload</h4>
        <div style={styles.field}>
          <label style={styles.label}>Folder Name (used for MinIO path)</label>
          <input
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            placeholder="e.g. Lecture_01"
            style={styles.input}
          />
        </div>
      </div>

      {/* Folder Selector */}
      <div style={styles.selectSection}>
        <label style={styles.label}>
          Select a folder of images to upload:
        </label>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          webkitdirectory="true"
          directory="true"
          onChange={handleFolderSelect}
          style={styles.fileInput}
        />
      </div>

      {/* Per-Image Annotation Table */}
      {selectedFiles.length > 0 && (
        <div style={styles.tableSection}>
          <h4 style={styles.sectionTitle}>
            🖊️ Annotate Images ({selectedFiles.length} images selected)
          </h4>
          <p style={styles.hint}>
            Enter the text visible on the board for each image. Leave blank to
            skip annotation.
          </p>
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>#</th>
                  <th style={styles.th}>Preview</th>
                  <th style={styles.th}>Filename</th>
                  <th style={{ ...styles.th, minWidth: 250 }}>
                    Board Text / Content
                  </th>
                  <th style={styles.th}>Class</th>
                </tr>
              </thead>
              <tbody>
                {selectedFiles.map((file, idx) => (
                  <tr key={file.name} style={styles.tr}>
                    <td style={styles.td}>{idx + 1}</td>
                    <td style={styles.td}>
                      <img
                        src={URL.createObjectURL(file)}
                        alt={file.name}
                        style={styles.preview}
                      />
                    </td>
                    <td style={{ ...styles.td, fontSize: 12, color: "#94a3b8" }}>
                      {file.name}
                    </td>
                    <td style={styles.td}>
                      <input
                        value={annotations[file.name]?.text || ""}
                        onChange={(e) =>
                          updateAnnotation(file.name, "text", e.target.value)
                        }
                        placeholder="e.g. x² + y² = r²"
                        style={styles.annInput}
                      />
                    </td>
                    <td style={styles.td}>
                      <select
                        value={annotations[file.name]?.class || "Text"}
                        onChange={(e) =>
                          updateAnnotation(file.name, "class", e.target.value)
                        }
                        style={styles.classSelect}
                      >
                        {CLASSES.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Upload Button */}
          <button
            onClick={handleUpload}
            style={{
              ...styles.btn,
              opacity: loading ? 0.6 : 1,
              cursor: loading ? "not-allowed" : "pointer",
            }}
            disabled={loading}
          >
            {loading
              ? "⏳ Uploading to MinIO & MongoDB…"
              : `🚀 Upload ${selectedFiles.length} Images`}
          </button>
        </div>
      )}

      {/* Status Message */}
      {status && (
        <p
          style={{
            ...styles.status,
            color: status.ok ? "#10b981" : "#ef4444",
            background: status.ok
              ? "rgba(16,185,129,0.08)"
              : "rgba(239,68,68,0.08)",
          }}
        >
          {status.msg}
        </p>
      )}
    </div>
  );
}

const styles = {
  wrap: {
    background: "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)",
    border: "1px solid #1e293b",
    borderRadius: 14,
    padding: "24px 28px",
    display: "flex",
    flexDirection: "column",
    gap: 20,
  },
  metaSection: {
    background: "rgba(14, 165, 233, 0.06)",
    border: "1px solid #1e293b",
    borderRadius: 10,
    padding: "16px 18px",
  },
  selectSection: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  sectionTitle: {
    color: "#94a3b8",
    fontSize: 14,
    fontWeight: 600,
    margin: "0 0 12px 0",
    letterSpacing: "0.3px",
  },
  hint: {
    color: "#64748b",
    fontSize: 12,
    margin: "0 0 12px 0",
    fontStyle: "italic",
  },
  field: { display: "flex", flexDirection: "column", gap: 4 },
  label: { fontSize: 12, color: "#64748b", fontWeight: 500 },
  input: {
    background: "#0f172a",
    color: "#e2e8f0",
    border: "1px solid #334155",
    borderRadius: 6,
    padding: "9px 12px",
    fontSize: 14,
    width: "100%",
    boxSizing: "border-box",
  },
  fileInput: {
    background: "#0f172a",
    color: "#e2e8f0",
    border: "1px solid #334155",
    borderRadius: 6,
    padding: "8px 10px",
    fontSize: 13,
    width: "100%",
    boxSizing: "border-box",
  },
  tableSection: {
    background: "rgba(14, 165, 233, 0.04)",
    border: "1px solid #1e293b",
    borderRadius: 10,
    padding: "16px 18px",
  },
  tableWrap: {
    maxHeight: 420,
    overflowY: "auto",
    borderRadius: 8,
    border: "1px solid #1e293b",
    marginBottom: 16,
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  th: {
    background: "#0f172a",
    color: "#64748b",
    padding: "10px 12px",
    textAlign: "left",
    fontWeight: 600,
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: "0.5px",
    position: "sticky",
    top: 0,
    zIndex: 1,
    borderBottom: "1px solid #1e293b",
  },
  tr: {
    borderBottom: "1px solid #1e293b22",
  },
  td: {
    padding: "8px 12px",
    verticalAlign: "middle",
  },
  preview: {
    width: 52,
    height: 36,
    objectFit: "cover",
    borderRadius: 4,
    border: "1px solid #334155",
  },
  annInput: {
    background: "#0f172a",
    color: "#e2e8f0",
    border: "1px solid #334155",
    borderRadius: 5,
    padding: "7px 10px",
    fontSize: 13,
    width: "100%",
    boxSizing: "border-box",
  },
  classSelect: {
    background: "#0f172a",
    color: "#e2e8f0",
    border: "1px solid #334155",
    borderRadius: 5,
    padding: "7px 8px",
    fontSize: 12,
  },
  btn: {
    padding: "12px 28px",
    borderRadius: 8,
    border: "none",
    background: "linear-gradient(135deg, #0ea5e9, #06b6d4)",
    color: "#fff",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 15,
    transition: "opacity 0.2s",
    width: "100%",
  },
  status: {
    marginTop: 4,
    fontSize: 14,
    fontWeight: 500,
    padding: "12px 16px",
    borderRadius: 8,
    border: "1px solid transparent",
  },
};
