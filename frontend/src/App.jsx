import React, { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

mermaid.initialize({ startOnLoad: false, theme: 'neutral' })

const STAGES = {
  queued: 'Queued', extracting: 'Extracting frames', deduping: 'Selecting keyframes',
  recognizing: 'Recognizing screens (LLM)', analyzing: 'Building flow & findings',
  done: 'Done', error: 'Error',
}
const SEV_COLOR = { high: '#d33', mid: '#e8a13a', low: '#888', info: '#4a90d9' }

export default function App() {
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')

  async function upload(file) {
    setError('')
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/analyses', { method: 'POST', body: form })
    if (!res.ok) { setError((await res.json()).detail || res.statusText); return }
    const { job_id } = await res.json()
    poll(job_id)
  }

  function poll(id) {
    const tick = async () => {
      const res = await fetch(`/api/analyses/${id}`)
      if (!res.ok) { setError('Job not found'); return }
      const j = await res.json()
      setJob(j)
      if (j.status !== 'done' && j.status !== 'error') setTimeout(tick, 1500)
    }
    tick()
  }

  return (
    <div className="wrap">
      <h1>User Flow Analyzer</h1>
      <p className="sub">Upload an app screen recording → automated user-flow analysis</p>
      {error && <div className="error">{error}</div>}
      {!job && <Uploader onFile={upload} />}
      {job && job.status !== 'done' && job.status !== 'error' && <Progress job={job} />}
      {job?.status === 'error' && <div className="error">Analysis failed: {job.error}</div>}
      {job?.status === 'done' && <Results job={job} onReset={() => setJob(null)} />}
    </div>
  )
}

function Uploader({ onFile }) {
  const [drag, setDrag] = useState(false)
  return (
    <label
      className={`drop ${drag ? 'drag' : ''}`}
      onDragOver={e => { e.preventDefault(); setDrag(true) }}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); e.dataTransfer.files[0] && onFile(e.dataTransfer.files[0]) }}
    >
      <input type="file" accept=".mp4,.mov,.webm" hidden
        onChange={e => e.target.files[0] && onFile(e.target.files[0])} />
      <strong>Drop a recording here</strong> or click to choose (mp4 / mov / webm)
    </label>
  )
}

function Progress({ job }) {
  return (
    <div className="card">
      <div className="bar"><div style={{ width: `${job.progress}%` }} /></div>
      <p>{STAGES[job.status] ?? job.status} — {job.progress}%</p>
    </div>
  )
}

function Results({ job, onReset }) {
  const [tab, setTab] = useState('flow')
  const r = job.result
  return (
    <div>
      <div className="summary card">
        <strong>{r.video_name}</strong> · {Math.round(r.duration)}s · {r.summary}
        <button className="ghost" onClick={onReset}>New analysis</button>
      </div>
      <nav className="tabs">
        {[['flow', 'Flow diagram'], ['screens', 'Screen inventory'],
          ['events', 'Action log'], ['findings', 'UX findings']].map(([k, label]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{label}</button>
        ))}
      </nav>
      {tab === 'flow' && <Mermaid code={r.mermaid} />}
      {tab === 'screens' && <Screens job={job} />}
      {tab === 'events' && <Events r={r} />}
      {tab === 'findings' && <Findings r={r} />}
    </div>
  )
}

function Mermaid({ code }) {
  const ref = useRef(null)
  useEffect(() => {
    let cancelled = false
    mermaid.render(`m${Date.now()}`, code)
      .then(({ svg }) => { if (!cancelled && ref.current) ref.current.innerHTML = svg })
      .catch(() => { if (ref.current) ref.current.textContent = code })
    return () => { cancelled = true }
  }, [code])
  return (
    <div className="card">
      <div ref={ref} className="mermaid-box" />
      <details><summary>Mermaid source</summary><pre>{code}</pre></details>
    </div>
  )
}

function Screens({ job }) {
  const { screens } = job.result
  return (
    <div className="grid">
      {screens.map(s => (
        <div key={s.id} className="card screen">
          <img src={`/api/analyses/${job.id}/frames/${s.representative_frame}`} alt={s.name} loading="lazy" />
          <div>
            <strong>{s.id} · {s.name}</strong>
            <span className="badge">{s.type}</span>
            <p className="muted">{s.elements.join(' · ')}</p>
            <p className="muted">seen at {s.appearances.slice(0, 6).map(t => `${Math.round(t)}s`).join(', ')}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function Events({ r }) {
  const names = Object.fromEntries(r.screens.map(s => [s.id, s.name]))
  return (
    <table className="card table">
      <thead><tr><th>t</th><th>screen</th><th>action</th><th>target</th><th>note</th></tr></thead>
      <tbody>
        {r.events.map((e, i) => (
          <tr key={i} className={e.action === 'secure' ? 'secure' : ''}>
            <td>{e.timestamp.toFixed(1)}s</td>
            <td>{names[e.screen_id] ?? e.screen_id}</td>
            <td>{e.action}{e.confidence === 'estimated' ? ' *' : ''}</td>
            <td>{e.target}</td><td>{e.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Findings({ r }) {
  if (!r.findings.length) return <p className="card">No findings — clean session!</p>
  return (
    <div>
      {r.findings.map((f, i) => (
        <div key={i} className="card finding" style={{ borderLeftColor: SEV_COLOR[f.severity] }}>
          <strong>[{f.severity.toUpperCase()}] {f.title}</strong>
          <p className="muted">{f.evidence}</p>
          {f.suggestion && <p>{f.suggestion}</p>}
          {f.timestamps.length > 0 &&
            <p className="muted">at {f.timestamps.map(t => `${Math.round(t)}s`).join(', ')}</p>}
        </div>
      ))}
      <p className="muted">* Findings are based on a single recording (n=1) — validate before generalizing.</p>
    </div>
  )
}
