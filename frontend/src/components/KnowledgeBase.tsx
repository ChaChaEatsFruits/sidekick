import { useEffect, useRef, useState } from "react";
import { listKb, reindexKb, uploadKb } from "../api";

export function KnowledgeBase() {
  const [files, setFiles] = useState<string[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listKb().then((kb) => setFiles(kb.files), (e: Error) => setError(e.message));
  }, []);

  // Same as the old "Add and re-index" button: copy any chosen files into kb/, then rebuild the index.
  async function addAndReindex() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const chosen = picker.current?.files;
      if (chosen && chosen.length > 0) await uploadKb(chosen);
      const result = await reindexKb();
      setFiles(result.files);
      setNote(`Indexed ${result.chunks} chunks from ${result.files.length} files`);
      if (picker.current) picker.current.value = "";
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="kb">
      <summary>Knowledge base <span className="count">{files.length} files</span></summary>
      <ul>
        {files.map((file) => (
          <li key={file}>{file}</li>
        ))}
      </ul>
      <input ref={picker} type="file" multiple accept=".pdf,.md,.txt" aria-label="Add PDF, Markdown or text files" />
      <button className="secondary" disabled={busy} onClick={addAndReindex}>
        {busy ? "Indexing…" : "Add and re-index"}
      </button>
      {note && <p className="note">{note}</p>}
      {error && <p className="error">{error}</p>}
    </details>
  );
}
