import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Loader, useToast } from "../components/ui";

function humanSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${units[i]}`;
}

export default function Attachments() {
  const [rows, setRows] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef();
  const toast = useToast();

  const load = () => api.attachments.list().then(setRows);
  useEffect(() => { load(); }, []);

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", file.name);
      await api.attachments.create(fd);
      toast("File uploaded");
      load();
    } catch (e) { toast(`Upload failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setUploading(false); if (fileInput.current) fileInput.current.value = ""; }
  };

  const remove = async (row) => {
    if (!confirm(`Delete "${row.name}"?`)) return;
    await api.attachments.remove(row.id);
    toast("Deleted");
    load();
  };

  if (!rows) return <Loader />;

  return (
    <div className="grid">
      <div className="section-head">
        <span className="page-sub">Files you can attach to auto-replies (set them per rule on the Rules page).</span>
        <button className="btn btn-primary" onClick={() => fileInput.current?.click()} disabled={uploading}>
          <Icon.plus /> {uploading ? "Uploading…" : "Upload file"}
        </button>
        <input ref={fileInput} type="file" hidden onChange={(e) => upload(e.target.files[0])} />
      </div>

      <div
        className="card"
        style={{ padding: 28, border: "1.5px dashed var(--border-strong)", textAlign: "center", cursor: "pointer" }}
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files[0]); }}
      >
        <div className="page-sub">Drag & drop a file here, or click to browse</div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
        {rows.map((a) => (
          <div className="card card-pad" key={a.id}>
            <div className="row" style={{ marginBottom: 8 }}>
              <div className="brand-logo" style={{ width: 34, height: 34, fontSize: 14 }}><Icon.attachments /></div>
              <div style={{ minWidth: 0 }}>
                <div className="subj" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</div>
                <div className="muted">{humanSize(a.size)} · {a.content_type || "file"}</div>
              </div>
            </div>
            {a.description && <div className="page-sub" style={{ marginBottom: 8 }}>{a.description}</div>}
            <div className="row" style={{ justifyContent: "space-between" }}>
              <a className="btn btn-sm" href={a.file_url} target="_blank" rel="noreferrer">Download</a>
              <button className="btn btn-sm btn-danger" onClick={() => remove(a)}><Icon.trash /></button>
            </div>
          </div>
        ))}
        {rows.length === 0 && <div className="card empty" style={{ gridColumn: "1 / -1" }}>No attachments yet.</div>}
      </div>
    </div>
  );
}
