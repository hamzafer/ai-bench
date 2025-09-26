import { useEffect, useMemo, useState } from 'react';
import './App.css';

const FIELD_LABELS = [
  { key: 'patient_prioritized', label: 'Prioritized' },
  { key: 'patient_ready', label: 'Ready' },
  { key: 'patient_short_notice', label: 'Short Notice' },
];

const normalizeValue = (value) => {
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (value === null || value === undefined || value === '') return 'null';
  return String(value).toLowerCase();
};

function App() {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [rowLoading, setRowLoading] = useState(null);
  const [error, setError] = useState('');

  const loadResults = async () => {
    setError('');
    try {
      const response = await fetch('/api/results');
      if (!response.ok) {
        throw new Error(`Failed to fetch results (${response.status})`);
      }
      const payload = await response.json();
      setRows(payload.rows || []);
      setSummary(payload.summary || null);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadResults();
  }, []);

  const runBenchmark = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/run-benchmark', {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Benchmark failed');
      }
      const payload = await response.json();
      setSummary(payload.summary || null);
      await loadResults();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const metrics = useMemo(() => summary?.metrics || [], [summary]);
  const latency = summary?.latency_stats;

  const runRow = async (rowId) => {
    setRowLoading(rowId);
    setError('');
    try {
      const response = await fetch(`/api/run-row/${rowId}`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Row benchmark failed');
      }
      const payload = await response.json();
      if (payload.summary) {
        setSummary(payload.summary);
      }
      if (payload.row) {
        setRows((prev) =>
          prev.map((item) => (item.id === rowId ? payload.row : item)),
        );
      } else {
        await loadResults();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setRowLoading(null);
    }
  };

  return (
    <div className="app">
      <header className="app__header">
        <h1>Comment Benchmark Dashboard</h1>
        <button className="app__action" onClick={runBenchmark} disabled={loading}>
          {loading ? 'Running…' : 'Run Benchmark'}
        </button>
      </header>

      {error && <div className="app__error">{error}</div>}

      <section className="metrics">
        {metrics.map((metric) => (
          <div key={metric.field} className="metric-card">
            <h3>{metric.field}</h3>
            <p className="metric-card__value">{(metric.accuracy * 100).toFixed(1)}%</p>
            <p className="metric-card__details">
              {metric.correct}/{metric.total} correct
            </p>
          </div>
        ))}
        {latency && (
          <div className="metric-card">
            <h3>Latency (ms)</h3>
            <p className="metric-card__value">{latency.mean_ms.toFixed(0)}</p>
            <p className="metric-card__details">
              median {latency.median_ms.toFixed(0)} · p95 {latency.p95_ms.toFixed(0)} · max {latency.max_ms.toFixed(0)}
            </p>
          </div>
        )}
      </section>

      <section className="table-section">
        <h2>Rows ({rows.length})</h2>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>No.</th>
                <th>Comment</th>
                {FIELD_LABELS.map((field) => (
                  <th key={field.key}>{field.label}</th>
                ))}
                <th>Availability Periods</th>
                <th>Latency (ms)</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const prediction = row.prediction || {};
                const truthAvailability = normalizeValue(
                  row.truth.availability_periods === 'null'
                    ? null
                    : row.truth.availability_periods && row.truth.availability_periods !== 'null'
                    ? 'list'
                    : row.truth.availability_periods,
                );
                const predAvailability = prediction.availability_periods && prediction.availability_periods.length
                  ? 'list'
                  : 'null';
                const availabilityMatch = truthAvailability === predAvailability;

                return (
                  <tr key={row.id}>
                    <td>{row.row_number ?? index + 1}</td>
                    <td className="comment-cell">{row.comment_text}</td>
                    {FIELD_LABELS.map(({ key }) => {
                      const truthValue = normalizeValue(row.truth[key]);
                      const predValue = normalizeValue(prediction[key]);
                      const match = truthValue === predValue;
                      const className = match ? 'match-true' : 'match-false';
                      return (
                        <td key={key} className={className}>
                          <div className="value-pair">
                            <span className="value-pair__truth">
                              <span className="value-pair__label">Truth:</span> {truthValue}
                            </span>
                            <span className="value-pair__pred">
                              <span className="value-pair__label">Prediction:</span> {predValue}
                            </span>
                          </div>
                        </td>
                      );
                    })}
                    <td className={availabilityMatch ? 'match-true' : 'match-false'}>
                      <div className="value-pair">
                        <span className="value-pair__truth">
                          <span className="value-pair__label">Truth:</span> {row.truth.availability_periods}
                        </span>
                        <span className="value-pair__pred">
                          <span className="value-pair__label">Prediction:</span>{' '}
                          {prediction.availability_periods ? JSON.stringify(prediction.availability_periods) : 'null'}
                        </span>
                      </div>
                    </td>
                    <td>{row.latency_ms ? row.latency_ms.toFixed(0) : '—'}</td>
                    <td>
                      <button
                        className="row-action"
                        onClick={() => runRow(row.id)}
                        disabled={loading || rowLoading === row.id}
                      >
                        {rowLoading === row.id ? 'Updating…' : 'Re-run'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default App;
