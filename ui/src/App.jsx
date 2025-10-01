import { Fragment, useEffect, useMemo, useState } from 'react';
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

const formatPercent = (value) =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(0)}%`;

const computeDeterminismStats = (detail) => {
  const { runs = [], truth = {} } = detail || {};
  if (!runs.length) return null;

  const latencies = runs
    .map((run) => run.latency_ms)
    .filter((value) => typeof value === 'number' && !Number.isNaN(value));

  const latencyStats = latencies.length
    ? {
        mean_ms: latencies.reduce((sum, value) => sum + value, 0) / latencies.length,
        min_ms: Math.min(...latencies),
        max_ms: Math.max(...latencies),
      }
    : null;

  const fieldStats = FIELD_LABELS.map(({ key, label }) => {
    const truthValue = normalizeValue(truth[key]);
    const counts = new Map();
    let matchCount = 0;
    runs.forEach((run) => {
      const value = normalizeValue(run.prediction?.[key]);
      counts.set(value, (counts.get(value) ?? 0) + 1);
      if (value === truthValue) {
        matchCount += 1;
      }
    });
    const distribution = Array.from(counts.entries())
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count);
    return {
      key,
      label,
      truth_value: truthValue,
      match_count: matchCount,
      total: runs.length,
      match_rate: matchCount / runs.length,
      distribution,
    };
  });

  const availabilityStats = (() => {
    const truthAvailability = normalizeValue(
      truth.availability_periods === 'null'
        ? null
        : truth.availability_periods && truth.availability_periods !== 'null'
        ? 'list'
        : truth.availability_periods,
    );
    const counts = new Map();
    let matchCount = 0;
    runs.forEach((run) => {
      const predAvailability =
        run.prediction?.availability_periods && run.prediction.availability_periods.length ? 'list' : 'null';
      const value = normalizeValue(predAvailability);
      counts.set(value, (counts.get(value) ?? 0) + 1);
      if (value === truthAvailability) {
        matchCount += 1;
      }
    });
    const distribution = Array.from(counts.entries())
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count);
    return {
      label: 'Availability',
      truth_value: truthAvailability,
      match_count: matchCount,
      total: runs.length,
      match_rate: matchCount / runs.length,
      distribution,
    };
  })();

  return {
    latency: latencyStats,
    fields: fieldStats,
    availability: availabilityStats,
  };
};

function App() {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [rowLoading, setRowLoading] = useState(null);
  const [deterministicLoading, setDeterministicLoading] = useState(null);
  const [expandedRow, setExpandedRow] = useState(null);
  const [deterministicCounts, setDeterministicCounts] = useState({});
  const [deterministicResults, setDeterministicResults] = useState({});
  const [deterministicDetailLoading, setDeterministicDetailLoading] = useState(null);
  const [determinismSummary, setDeterminismSummary] = useState(null);
  const [determinismGlobalCount, setDeterminismGlobalCount] = useState(5);
  const [determinismGlobalLoading, setDeterminismGlobalLoading] = useState(false);
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

  const loadDeterminismSummary = async () => {
    try {
      const response = await fetch('/api/determinism-summary');
      if (!response.ok) {
        throw new Error(`Failed to fetch determinism summary (${response.status})`);
      }
      const payload = await response.json();
      setDeterminismSummary(payload);
    } catch (err) {
      console.error('Determinism summary error', err);
    }
  };

  const loadDeterminismDetail = async (rowId, limit = 50) => {
    setDeterministicDetailLoading(rowId);
    try {
      const response = await fetch(`/api/determinism/${rowId}?limit=${limit}`);
      if (!response.ok) {
        throw new Error('Failed to load determinism detail');
      }
      const payload = await response.json();
      setDeterministicResults((prev) => ({ ...prev, [rowId]: payload }));
    } catch (err) {
      setError(err.message);
    } finally {
      setDeterministicDetailLoading(null);
    }
  };

  useEffect(() => {
    loadResults();
    loadDeterminismSummary();
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
      await loadDeterminismSummary();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const metrics = useMemo(() => summary?.metrics || [], [summary]);
  const latency = summary?.latency_stats;
  const determinismRows = useMemo(() => determinismSummary?.rows || [], [determinismSummary]);
  const overallDeterminism = determinismSummary?.overall;
  const topDeterminismRows = useMemo(() => {
    if (!determinismSummary?.rows) {
      return [];
    }
    return [...determinismSummary.rows]
      .map((row) => ({
        ...row,
        minMatch: row.lowest_match_rate ?? 1,
      }))
      .sort((a, b) => a.minMatch - b.minMatch)
      .slice(0, 5);
  }, [determinismSummary]);

  const setCountForRow = (rowId, value) => {
    setDeterministicCounts((prev) => ({ ...prev, [rowId]: value }));
  };

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

const runRowBatch = async (rowId, count) => {
  setDeterministicLoading(rowId);
  setError('');
  try {
    const response = await fetch(`/api/run-row/${rowId}/batch?count=${count}&limit=50`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Determinism check failed');
      }
      const payload = await response.json();
      setDeterministicResults((prev) => ({ ...prev, [rowId]: payload }));
      setExpandedRow(rowId);
      await loadDeterminismSummary();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeterministicLoading(null);
    }
  };

  const runDeterminismAll = async () => {
    setDeterminismGlobalLoading(true);
    setError('');
    try {
      const response = await fetch(
        `/api/run-determinism-all?count=${determinismGlobalCount}&limit=50`,
        {
          method: 'POST',
        },
      );
      if (!response.ok) {
        throw new Error('Determinism run failed');
      }
      const payload = await response.json();
      setDeterminismSummary(payload.summary || null);
      setDeterministicResults({});
      setExpandedRow(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setDeterminismGlobalLoading(false);
    }
  };

  const toggleExpandedRow = (rowId) => {
    const nextRow = expandedRow === rowId ? null : rowId;
    setExpandedRow(nextRow);
    if (nextRow && !deterministicResults[rowId]) {
      loadDeterminismDetail(rowId);
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

      <section className="determinism-overview">
        <div className="determinism-overview__header">
          <h2>Determinism</h2>
          <div className="batch-actions">
            <select
              value={determinismGlobalCount}
              onChange={(event) => setDeterminismGlobalCount(Number(event.target.value))}
              disabled={determinismGlobalLoading || loading}
            >
              {[1, 5, 10].map((value) => (
                <option key={value} value={value}>
                  {value}×
                </option>
              ))}
            </select>
            <button
              className="row-action secondary"
              onClick={runDeterminismAll}
              disabled={determinismGlobalLoading || loading}
            >
              {determinismGlobalLoading ? 'Running…' : 'Run all'}
            </button>
            <button
              className="row-expand determinism-refresh"
              onClick={loadDeterminismSummary}
              disabled={determinismGlobalLoading || loading}
            >
              Refresh
            </button>
          </div>
        </div>
        {overallDeterminism ? (
          <>
            <div className="metrics determinism-overview__cards">
              <div className="metric-card">
                <h3>Rows Tested</h3>
                <p className="metric-card__value">
                  {overallDeterminism.rows_with_runs}/{overallDeterminism.total_rows}
                </p>
                <p className="metric-card__details">{overallDeterminism.total_runs} runs stored</p>
              </div>
              {overallDeterminism.latency && (
                <div className="metric-card">
                  <h3>Latency (ms)</h3>
                  <p className="metric-card__value">
                    {overallDeterminism.latency.mean_ms.toFixed(0)}
                  </p>
                  <p className="metric-card__details">
                    min {overallDeterminism.latency.min_ms.toFixed(0)} · max{' '}
                    {overallDeterminism.latency.max_ms.toFixed(0)}
                  </p>
                </div>
              )}
            </div>
            <div className="determinism-overview__field-summary">
              <h4>Field match rates</h4>
              <ul>
                {(overallDeterminism?.fields || []).map((field) => (
                  <li key={field.key}>
                    <strong>{field.label}:</strong>{' '}
                    {field.rows_measured ? (
                      <>
                        avg {formatPercent(field.average_match_rate)} · worst{' '}
                        {formatPercent(field.worst_match_rate)} ({field.rows_measured} rows)
                      </>
                    ) : (
                      '—'
                    )}
                  </li>
                ))}
                {overallDeterminism?.availability && (
                  <li>
                    <strong>{overallDeterminism.availability.label}:</strong>{' '}
                    {overallDeterminism.availability.rows_measured ? (
                      <>
                        avg {formatPercent(overallDeterminism.availability.average_match_rate)} · worst{' '}
                        {formatPercent(overallDeterminism.availability.worst_match_rate)} ({
                          overallDeterminism.availability.rows_measured
                        }{' '}
                        rows)
                      </>
                    ) : (
                      '—'
                    )}
                  </li>
                )}
              </ul>
            </div>
            {topDeterminismRows.length > 0 && (
              <div className="table-wrapper determinism-overview__table">
                <table>
                  <thead>
                    <tr>
                      <th>No.</th>
                      <th>Comment</th>
                      <th>Runs</th>
                      <th>Lowest match</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topDeterminismRows.map((row) => (
                      <tr key={row.row_id}>
                        <td>{row.row_number}</td>
                        <td className="comment-cell">
                          {row.comment_text?.length > 120
                            ? `${row.comment_text.slice(0, 120)}…`
                            : row.comment_text}
                        </td>
                        <td>{row.total_runs}</td>
                        <td>{formatPercent(row.minMatch)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <p className="determinism-overview__empty">No determinism runs yet. Use the controls above to start.</p>
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

                const batchCount = deterministicCounts[row.id] ?? 5;
                const detail = deterministicResults[row.id];
                const stats = detail?.stats || (detail ? computeDeterminismStats(detail) : null);
                const isExpanded = expandedRow === row.id;

                return (
                  <Fragment key={row.id}>
                  <tr>
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
                      <div className="action-stack">
                        <button
                          className="row-action"
                          onClick={() => runRow(row.id)}
                          disabled={loading || rowLoading === row.id}
                        >
                          {rowLoading === row.id ? 'Updating…' : 'Re-run'}
                        </button>
                        <div className="batch-actions">
                          <select
                            value={batchCount}
                            onChange={(event) => setCountForRow(row.id, Number(event.target.value))}
                            disabled={deterministicLoading === row.id || loading}
                          >
                            {[1, 5, 10].map((value) => (
                              <option key={value} value={value}>
                                {value}×
                              </option>
                            ))}
                          </select>
                          <button
                            className="row-action secondary"
                            onClick={() => runRowBatch(row.id, batchCount)}
                            disabled={deterministicLoading === row.id || loading}
                          >
                            {deterministicLoading === row.id ? 'Running…' : 'Determinism'}
                          </button>
                        </div>
                        <button
                          className="row-expand"
                          onClick={() => toggleExpandedRow(row.id)}
                        >
                          {isExpanded ? 'Hide details' : 'Show details'}
                        </button>
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="deterministic-detail">
                      <td colSpan={8}>
                        <div className="deterministic-panel">
                          <h4>Determinism Check</h4>
                          {deterministicLoading === row.id && <p>Running…</p>}
                          {deterministicDetailLoading === row.id && !detail && <p>Loading stored runs…</p>}
                          {deterministicLoading !== row.id && deterministicDetailLoading !== row.id && (!detail || detail.runs?.length === 0) && (
                            <p>No runs yet. Choose a count and press Determinism.</p>
                          )}
                          {deterministicLoading !== row.id && deterministicDetailLoading !== row.id && detail?.total_runs ? (
                            <p className="deterministic-total">Total runs stored: {detail.total_runs}</p>
                          ) : null}
                          {deterministicLoading !== row.id && deterministicDetailLoading !== row.id && stats && detail?.runs?.length > 0 && (
                            <div className="deterministic-runs">
                              <div className="deterministic-summary">
                                {stats.latency && (
                                  <div className="deterministic-summary-item">
                                    <h5>Latency</h5>
                                    <p>
                                      mean {stats.latency.mean_ms.toFixed(0)} ms · min {stats.latency.min_ms.toFixed(0)}
                                      ms · max {stats.latency.max_ms.toFixed(0)} ms
                                    </p>
                                  </div>
                                )}
                                <div className="deterministic-summary-item">
                                  <h5>Field agreement</h5>
                                  <ul>
                                    {(stats.fields || []).map((field) => (
                                      <li key={field.key}>
                                        <strong>{field.label}:</strong> {field.match_count}/{field.total} match Truth ({
                                          formatPercent(field.match_rate)
                                        }) · values:{' '}
                                        {field.distribution
                                          .map((item) => `${item.value}×${item.count}`)
                                          .join(', ')}
                                      </li>
                                    ))}
                                    {stats.availability && (
                                      <li>
                                        <strong>{stats.availability.label}:</strong>{' '}
                                        {stats.availability.match_count}/{stats.availability.total} match Truth ({
                                          formatPercent(stats.availability.match_rate)
                                        }) · values:{' '}
                                        {stats.availability.distribution
                                          .map((item) => `${item.value}×${item.count}`)
                                          .join(', ')}
                                      </li>
                                    )}
                                  </ul>
                                </div>
                              </div>
                              {detail.runs.map((run) => (
                                <div key={run.attempt ?? `${run.start_time}-${run.latency_ms}`} className="deterministic-run-card">
                                  <div className="deterministic-run-header">
                                    <span>Attempt {run.attempt ?? '-'}</span>
                                    <span>
                                      {typeof run.latency_ms === 'number'
                                        ? `${run.latency_ms.toFixed(0)} ms`
                                        : '—'}
                                    </span>
                                  </div>
                                  <div className="deterministic-run-body">
                                    {FIELD_LABELS.map(({ key, label }) => (
                                      <div key={key} className="deterministic-run-field">
                                        <span className="deterministic-run-label">{label}:</span>
                                        <span className="deterministic-run-value">
                                          {normalizeValue(run.prediction?.[key])}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
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
