import { useState, useRef } from "react";

const MAX_PROMPT_LENGTH = 8000;

export default function PromptForm({ onSubmit, isSubmitting }) {
  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState(null);
  const [fileText, setFileText] = useState(null);
  const [validationError, setValidationError] = useState(null);
  const fileInputRef = useRef(null);

  function validate() {
    if (!prompt.trim()) {
      return "Enter a prompt before sending it to the sandbox.";
    }
    if (prompt.length > MAX_PROMPT_LENGTH) {
      return `Prompt is too long (${prompt.length}/${MAX_PROMPT_LENGTH} characters).`;
    }
    return null;
  }

  async function handleFileChange(e) {
    const selected = e.target.files?.[0];
    if (!selected) return;

    const allowed = [".txt", ".md", ".html", ".csv"];
    const ext = selected.name.slice(selected.name.lastIndexOf(".")).toLowerCase();
    if (!allowed.includes(ext)) {
      setValidationError(`Unsupported file type "${ext}". Allowed: ${allowed.join(", ")}`);
      e.target.value = "";
      return;
    }

    setValidationError(null);
    setFile(selected);
    const text = await selected.text();
    setFileText(text);
  }

  function clearFile() {
    setFile(null);
    setFileText(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleSubmit(e) {
    e.preventDefault();
    const err = validate();
    if (err) {
      setValidationError(err);
      return;
    }
    setValidationError(null);
    onSubmit({
      prompt: prompt.trim(),
      fileName: file?.name,
      fileText: fileText ?? undefined,
    });
  }

  return (
    <form className="prompt-form" onSubmit={handleSubmit}>
      <label className="field-label" htmlFor="prompt-input">
        Prompt to send through the sandbox
      </label>
      <textarea
        id="prompt-input"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="e.g. Summarize the attached document for me."
        rows={5}
        disabled={isSubmitting}
      />
      <div className="field-meta">
        <span className={prompt.length > MAX_PROMPT_LENGTH ? "char-count over" : "char-count"}>
          {prompt.length}/{MAX_PROMPT_LENGTH}
        </span>
      </div>

      <div className="file-row">
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.html,.csv"
          onChange={handleFileChange}
          disabled={isSubmitting}
        />
        {file && (
          <button type="button" className="chip-remove" onClick={clearFile} disabled={isSubmitting}>
            {file.name} x
          </button>
        )}
      </div>

      {validationError && (
        <p className="form-error" role="alert">
          {validationError}
        </p>
      )}

      <button type="submit" className="submit-btn" disabled={isSubmitting}>
        {isSubmitting ? "Running through gates..." : "Send to sandbox"}
      </button>
    </form>
  );
}