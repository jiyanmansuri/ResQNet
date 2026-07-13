import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import { io } from 'socket.io-client';
import axios from 'axios';
import 'leaflet/dist/leaflet.css';

// ─────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────
const API_BASE   = process.env.REACT_APP_API_URL || 'http://localhost:5000';
const MAP_CENTER = [20.5937, 78.9629];
const MAX_INCIDENTS = 300;

const SEVERITY_CONFIG = {
  Critical: { color: '#ef4444', radius: 12, bg: '#450a0a', border: '#ef4444' },
  Serious:  { color: '#f97316', radius: 9,  bg: '#431407', border: '#f97316' },
  Stable:   { color: '#22c55e', radius: 6,  bg: '#052e16', border: '#22c55e' },
};

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────
const fmt = {
  time: (ts) => {
    try {
      return new Date(ts).toLocaleTimeString('en-IN', { hour12: false });
    } catch { return ts; }
  },
  date: (ts) => {
    try {
      return new Date(ts).toLocaleDateString('en-IN', { day:'2-digit', month:'short' });
    } catch { return ''; }
  },
  conf: (c) => `${Math.round((c || 0) * 100)}%`,
};

// ─────────────────────────────────────────────
// Inline styles (design system)
// ─────────────────────────────────────────────
const S = {
  root: {
    display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw',
    background: '#0f172a', color: '#e2e8f0',
    fontFamily: "'Inter', sans-serif", overflow: 'hidden',
  },

  /* ── Navbar ── */
  navbar: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 24px', height: 58,
    background: 'linear-gradient(90deg,#0f172a 0%,#1e1b4b 100%)',
    borderBottom: '1px solid #1e293b',
    flexShrink: 0, zIndex: 10,
  },
  navLeft: { display: 'flex', alignItems: 'center', gap: 12 },
  navLogo: {
    fontSize: 22, fontWeight: 800, letterSpacing: '-0.5px',
    background: 'linear-gradient(135deg,#60a5fa,#818cf8)',
    WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
  },
  navBadge: {
    fontSize: 10, fontWeight: 600, padding: '2px 8px',
    background: '#1d4ed8', color: '#bfdbfe',
    borderRadius: 99, letterSpacing: 1, textTransform: 'uppercase',
  },
  navSub: { fontSize: 12, color: '#64748b', marginLeft: 4 },
  navRight: { display: 'flex', alignItems: 'center', gap: 16 },
  navTime: {
    fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
    color: '#94a3b8', letterSpacing: 1,
  },
  liveDot: {
    display: 'inline-block', width: 8, height: 8,
    borderRadius: '50%', background: '#22c55e',
    boxShadow: '0 0 0 0 rgba(34,197,94,0.6)',
    animation: 'pulse-green 1.8s infinite',
  },

  /* ── Stat cards ── */
  statsRow: {
    display: 'grid', gridTemplateColumns: 'repeat(4,1fr)',
    gap: 12, padding: '10px 20px', flexShrink: 0,
  },
  card: (accent) => ({
    background: '#1e293b', borderRadius: 12,
    border: `1px solid ${accent}33`,
    padding: '12px 16px', position: 'relative', overflow: 'hidden',
    transition: 'transform 0.2s',
  }),
  cardGlow: (accent) => ({
    position: 'absolute', top: 0, left: 0, right: 0, height: 2,
    background: accent, borderRadius: '12px 12px 0 0',
  }),
  cardLabel: {
    fontSize: 11, fontWeight: 600, letterSpacing: 1,
    textTransform: 'uppercase', color: '#64748b', marginBottom: 4,
  },
  cardValue: (accent) => ({
    fontSize: 34, fontWeight: 800, color: accent,
    fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.1,
  }),
  cardSub: { fontSize: 11, color: '#475569', marginTop: 2 },

  /* ── Main area ── */
  main: { display: 'flex', flex: 1, gap: 0, overflow: 'hidden' },

  /* ── Map pane ── */
  mapPane: {
    flex: '0 0 60%', position: 'relative',
    borderRight: '1px solid #1e293b',
  },
  mapOverlay: {
    position: 'absolute', top: 10, left: 10, zIndex: 1000,
    background: 'rgba(15,23,42,0.85)', backdropFilter: 'blur(8px)',
    borderRadius: 8, padding: '6px 12px',
    border: '1px solid #1e293b', fontSize: 11, color: '#94a3b8',
    pointerEvents: 'none',
  },

  /* ── Feed pane ── */
  feedPane: {
    flex: '0 0 40%', display: 'flex', flexDirection: 'column',
    background: '#0f172a', overflow: 'hidden',
  },
  feedHeader: {
    padding: '12px 16px', borderBottom: '1px solid #1e293b',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    flexShrink: 0,
  },
  feedTitle: { fontSize: 13, fontWeight: 700, color: '#cbd5e1', letterSpacing: 0.5 },
  feedCount: {
    fontSize: 11, padding: '2px 8px', borderRadius: 99,
    background: '#1e293b', color: '#64748b', fontFamily: 'monospace',
  },
  feedScroll: { flex: 1, overflowY: 'auto', padding: '8px 12px' },

  /* ── Incident card ── */
  incidentCard: (sev, isNew) => ({
    background: isNew ? SEVERITY_CONFIG[sev]?.bg || '#1e293b' : '#1e293b',
    border: `1px solid ${isNew ? (SEVERITY_CONFIG[sev]?.border || '#334155') : '#1e293b'}`,
    borderRadius: 10, padding: '10px 12px', marginBottom: 8,
    transition: 'all 0.4s ease',
    animation: isNew ? 'slide-in 0.35s ease' : 'none',
  }),
  incidentTop: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 },
  badge: (sev) => ({
    fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 99,
    background: `${SEVERITY_CONFIG[sev]?.color}22`,
    color: SEVERITY_CONFIG[sev]?.color || '#94a3b8',
    border: `1px solid ${SEVERITY_CONFIG[sev]?.color}44`,
    letterSpacing: 0.5, textTransform: 'uppercase',
  }),
  deviceId: {
    fontSize: 13, fontWeight: 700, color: '#e2e8f0',
    fontFamily: "'JetBrains Mono', monospace",
  },
  timestamp: { fontSize: 10, color: '#475569', marginLeft: 'auto' },
  incidentGrid: {
    display: 'grid', gridTemplateColumns: '1fr 1fr 1fr',
    gap: 4,
  },
  metric: { display: 'flex', flexDirection: 'column', gap: 1 },
  metricLabel: { fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: 0.5 },
  metricValue: { fontSize: 12, fontWeight: 600, color: '#94a3b8', fontFamily: 'monospace' },

  /* ── Popup ── */
  popup: { fontSize: 12, lineHeight: 1.6, minWidth: 180 },
  popupTitle: { fontWeight: 700, fontSize: 14, marginBottom: 4 },

  /* ── Filter Tabs & Action Buttons ── */
  tabGroup: { display: 'flex', gap: 6, background: '#1e293b', padding: 4, borderRadius: 8 },
  tabBtn: (active) => ({
    background: active ? '#334155' : 'transparent',
    color: active ? '#cbd5e1' : '#64748b',
    border: 'none', padding: '4px 10px', borderRadius: 6,
    fontSize: 11, fontWeight: 600, cursor: 'pointer', transition: '0.2s',
  }),
  actionRow: { marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' },
  actionBtn: (dispatched) => ({
    background: dispatched ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
    color: dispatched ? '#4ade80' : '#ef4444',
    border: `1px solid ${dispatched ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
    padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700,
    cursor: dispatched ? 'default' : 'pointer', transition: '0.2s', textTransform: 'uppercase', letterSpacing: 0.5
  }),
};

// ─────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────

function LiveClock() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span style={S.navTime}>
      {time.toLocaleTimeString('en-IN', { hour12: false })} IST
    </span>
  );
}

function StatCard({ label, value, accent, sub, pulse }) {
  return (
    <div style={S.card(accent)}>
      <div style={S.cardGlow(accent)} />
      <div style={S.cardLabel}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <div style={S.cardValue(accent)}>{value}</div>
        {pulse && (
          <span style={{
            display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
            background: '#ef4444', boxShadow: '0 0 0 0 rgba(239,68,68,0.6)',
            animation: 'pulse-red 1.2s infinite',
          }} />
        )}
      </div>
      {sub && <div style={S.cardSub}>{sub}</div>}
    </div>
  );
}

function IncidentCard({ incident, isNew, isDispatched, onDispatch }) {
  const sev = incident.severity || 'Stable';
  const isHighPriority = sev === 'Critical' || sev === 'Serious';
  
  return (
    <div style={S.incidentCard(sev, isNew)}>
      <div style={S.incidentTop}>
        <span style={S.badge(sev)}>{sev}</span>
        <span style={S.deviceId}>{incident.device_id}</span>
        <span style={S.timestamp}>
          {fmt.date(incident.timestamp)} {fmt.time(incident.timestamp)}
        </span>
      </div>
      <div style={S.incidentGrid}>
        <div style={S.metric}>
          <span style={S.metricLabel}>Confidence</span>
          <span style={{ ...S.metricValue, color: SEVERITY_CONFIG[sev]?.color }}>
            {fmt.conf(incident.confidence)}
          </span>
        </div>
        <div style={S.metric}>
          <span style={S.metricLabel}>Flood</span>
          <span style={S.metricValue}>{(incident.flood_level || 0).toFixed(1)} m</span>
        </div>
        <div style={S.metric}>
          <span style={S.metricLabel}>AQI</span>
          <span style={{
            ...S.metricValue,
            color: incident.air_quality > 300 ? '#f97316' : '#94a3b8',
          }}>
            {incident.air_quality}
          </span>
        </div>
      </div>
      {incident.sos_active ? (
        <div style={{
          marginTop: 6, fontSize: 10, fontWeight: 700,
          color: '#ef4444', letterSpacing: 1,
          animation: 'pulse-text 1s infinite',
        }}>
          ● SOS ACTIVE — lat {(incident.lat || 0).toFixed(4)}, lon {(incident.lon || 0).toFixed(4)}
        </div>
      ) : (
        <div style={{ marginTop: 4, fontSize: 10, color: '#334155' }}>
          lat {(incident.lat || 0).toFixed(4)}, lon {(incident.lon || 0).toFixed(4)}
        </div>
      )}
      
      {isHighPriority && (
        <div style={S.actionRow}>
          <button 
            style={S.actionBtn(isDispatched)}
            onClick={() => {
              if (!isDispatched) onDispatch(incident);
            }}
          >
            {isDispatched ? '✓ Units Dispatched' : 'Dispatch Units'}
          </button>
        </div>
      )}
    </div>
  );
}

function MapMarker({ incident }) {
  const sev = incident.severity || 'Stable';
  const cfg = SEVERITY_CONFIG[sev];
  if (!incident.lat || !incident.lon) return null;

  return (
    <CircleMarker
      center={[incident.lat, incident.lon]}
      radius={cfg.radius}
      pathOptions={{
        color: cfg.color,
        fillColor: cfg.color,
        fillOpacity: incident.sos_active ? 0.95 : 0.65,
        weight: incident.sos_active ? 2.5 : 1.5,
      }}
    >
      <Popup>
        <div style={S.popup}>
          <div style={{ ...S.popupTitle, color: cfg.color }}>{sev}</div>
          <div><b>Device:</b> {incident.device_id}</div>
          <div><b>Confidence:</b> {fmt.conf(incident.confidence)}</div>
          <div><b>Flood Level:</b> {(incident.flood_level || 0).toFixed(2)} m</div>
          <div><b>AQI:</b> {incident.air_quality}</div>
          <div><b>SOS:</b> {incident.sos_active ? '🚨 YES' : 'No'}</div>
          <div style={{ marginTop: 4, fontSize: 10, color: '#6b7280' }}>
            {incident.timestamp}
          </div>
        </div>
      </Popup>
    </CircleMarker>
  );
}

// ─────────────────────────────────────────────
// Main App
// ─────────────────────────────────────────────
export default function App() {
  const [incidents, setIncidents]   = useState([]);
  const [stats, setStats]           = useState({ total: 0, critical: 0, serious: 0, stable: 0, active_sos: 0 });
  const [newIds, setNewIds]         = useState(new Set());
  const [connected, setConnected]   = useState(false);
  const [feedFilter, setFeedFilter] = useState('All');
  const [dispatchedIds, setDispatchedIds] = useState(new Set());
  const feedRef                     = useRef(null);
  const socketRef                   = useRef(null);

  // ── Recompute stats from local state (kept in sync with server stats) ──
  const recomputeStats = useCallback((list) => {
    const s = { total: list.length, critical: 0, serious: 0, stable: 0, active_sos: 0 };
    const cutoff = Date.now() - 60_000;
    list.forEach((inc) => {
      if (inc.severity === 'Critical') s.critical++;
      else if (inc.severity === 'Serious') s.serious++;
      else s.stable++;
      if (inc.sos_active && new Date(inc.timestamp).getTime() > cutoff) s.active_sos++;
    });
    setStats(s);
  }, []);

  // ── Initial data load ────────────────────────────────────────
  useEffect(() => {
    axios.get(`${API_BASE}/incidents`)
      .then((res) => {
        const data = res.data || [];
        setIncidents(data);
        recomputeStats(data);
      })
      .catch((err) => console.warn('[ResQNet] Could not fetch initial incidents:', err));
  }, [recomputeStats]);

  // ── Socket.IO connection ─────────────────────────────────────
  useEffect(() => {
    const socket = io(API_BASE, {
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
    });
    socketRef.current = socket;

    socket.on('connect',    () => { setConnected(true);  console.log('[WS] connected'); });
    socket.on('disconnect', () => { setConnected(false); console.log('[WS] disconnected'); });

    socket.on('new_incident', (incident) => {
      const id = `${incident.device_id}-${incident.timestamp}`;

      setIncidents((prev) => {
        const updated = [incident, ...prev].slice(0, MAX_INCIDENTS);
        recomputeStats(updated);
        return updated;
      });

      // Flash "new" highlight for 3 s
      setNewIds((prev) => {
        const next = new Set(prev);
        next.add(id);
        return next;
      });
      setTimeout(() => {
        setNewIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }, 3000);
    });

    return () => socket.disconnect();
  }, [recomputeStats]);

  // ── Deduplicate map markers (one per device, latest position) ───
  const mapMarkers = React.useMemo(() => {
    const seen = new Map();
    incidents.forEach((inc) => {
      if (!seen.has(inc.device_id)) seen.set(inc.device_id, inc);
    });
    return Array.from(seen.values());
  }, [incidents]);

  // ── Feed — Filter functionality ───────────────────────────────────────
  const sortedUniqueIncidents = React.useMemo(() => {
    const order = { 'Critical': 0, 'Serious': 1, 'Stable': 2 };
    return [...mapMarkers].sort((a, b) => 
      order[a.severity] - order[b.severity] || a.device_id.localeCompare(b.device_id)
    );
  }, [mapMarkers]);

  const filteredIncidents = feedFilter === 'All' 
    ? sortedUniqueIncidents 
    : sortedUniqueIncidents.filter(i => i.severity === 'Critical' || i.severity === 'Serious');
    
  const feedItems = filteredIncidents.slice(0, 150);

  const handleDispatch = useCallback((inc) => {
    alert(`DISPATCH INITIATED:\nDeploying rescue units to Device (${inc.device_id})\nLat: ${inc.lat?.toFixed(4)}, Lon: ${inc.lon?.toFixed(4)}\nSeverity: ${inc.severity}`);
    setDispatchedIds(prev => new Set(prev).add(inc.device_id));
  }, []);

  // ─────────────────────────────────────────────
  return (
    <>
      {/* ─── Global keyframe animations ─────────────────────── */}
      <style>{`
        @keyframes pulse-green {
          0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.6); }
          70%  { box-shadow: 0 0 0 8px rgba(34,197,94,0); }
          100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
        }
        @keyframes pulse-red {
          0%   { box-shadow: 0 0 0 0 rgba(239,68,68,0.7); }
          70%  { box-shadow: 0 0 0 10px rgba(239,68,68,0); }
          100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); }
        }
        @keyframes pulse-text {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.4; }
        }
        @keyframes slide-in {
          from { opacity: 0; transform: translateY(-8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .leaflet-container { background: #1e293b !important; }
        /* Dark scrollbar */
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }
      `}</style>

      <div style={S.root}>

        {/* ─── Navbar ─────────────────────────────────────────── */}
        <nav style={S.navbar}>
          <div style={S.navLeft}>
            <span style={S.navLogo}>ResQNet</span>
            <span style={S.navBadge}>Live</span>
            <span style={S.navSub}>Disaster Response Dashboard · India National View</span>
          </div>
          <div style={S.navRight}>
            <LiveClock />
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                ...S.liveDot,
                background: connected ? '#22c55e' : '#ef4444',
                animation: connected ? 'pulse-green 1.8s infinite' : 'pulse-red 1.2s infinite',
              }} />
              <span style={{ fontSize: 11, color: connected ? '#4ade80' : '#f87171' }}>
                {connected ? 'Connected' : 'Reconnecting…'}
              </span>
            </div>
          </div>
        </nav>

        {/* ─── Stat cards ─────────────────────────────────────── */}
        <div style={S.statsRow}>
          <StatCard
            label="Total Incidents"
            value={stats.total}
            accent="#60a5fa"
            sub="all time"
          />
          <StatCard
            label="Critical"
            value={stats.critical}
            accent="#ef4444"
            sub="severity level 2"
          />
          <StatCard
            label="Serious"
            value={stats.serious}
            accent="#f97316"
            sub="severity level 1"
          />
          <StatCard
            label="Active SOS"
            value={stats.active_sos}
            accent="#ef4444"
            sub="last 60 seconds"
            pulse
          />
        </div>

        {/* ─── Main area ──────────────────────────────────────── */}
        <div style={S.main}>

          {/* ── Map panel ─────────────────────────────────────── */}
          <div style={S.mapPane}>
            <div style={S.mapOverlay}>
              📍 India National Map · {mapMarkers.length} active devices
            </div>
            <MapContainer
              center={MAP_CENTER}
              zoom={5}
              style={{ height: '100%', width: '100%' }}
              zoomControl={true}
            >
              <TileLayer
                attribution='© <a href="https://www.openstreetmap.org/">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {mapMarkers.map((inc, i) => (
                <MapMarker key={`${inc.device_id}-${i}`} incident={inc} />
              ))}
            </MapContainer>

            {/* Legend */}
            <div style={{
              position: 'absolute', bottom: 16, left: 16, zIndex: 1000,
              background: 'rgba(15,23,42,0.9)', backdropFilter: 'blur(8px)',
              border: '1px solid #1e293b', borderRadius: 8,
              padding: '8px 12px', display: 'flex', gap: 14,
            }}>
              {Object.entries(SEVERITY_CONFIG).map(([sev, cfg]) => (
                <div key={sev} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <div style={{
                    width: cfg.radius + 4, height: cfg.radius + 4,
                    borderRadius: '50%', background: cfg.color, opacity: 0.8,
                  }} />
                  <span style={{ fontSize: 10, color: '#94a3b8' }}>{sev}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Incident feed ──────────────────────────────────── */}
          <div style={S.feedPane}>
            <div style={S.feedHeader}>
              <span style={S.feedTitle}>⚡ Live Incident Feed</span>
              <div style={S.tabGroup}>
                <button 
                  style={S.tabBtn(feedFilter === 'All')} 
                  onClick={() => setFeedFilter('All')}
                >
                  All
                </button>
                <button 
                  style={S.tabBtn(feedFilter === 'HighPriority')} 
                  onClick={() => setFeedFilter('HighPriority')}
                >
                  High Priority
                </button>
              </div>
              <span style={S.feedCount}>{feedItems.length} listed</span>
            </div>

            {feedItems.length === 0 ? (
              <div style={{
                flex: 1, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                color: '#334155', gap: 8,
              }}>
                <div style={{ fontSize: 32 }}>📡</div>
                <div style={{ fontSize: 13 }}>Waiting for sensor data…</div>
                <div style={{ fontSize: 11 }}>Make sure data_gen.py is running</div>
              </div>
            ) : (
              <div style={S.feedScroll} ref={feedRef}>
                {feedItems.map((inc) => {
                  const id = `${inc.device_id}-${inc.timestamp}`;
                  return (
                    <IncidentCard
                      key={inc.device_id}
                      incident={inc}
                      isNew={newIds.has(id)}
                      isDispatched={dispatchedIds.has(inc.device_id)}
                      onDispatch={handleDispatch}
                    />
                  );
                })}
              </div>
            )}

            {/* Footer strip */}
            <div style={{
              padding: '8px 14px', borderTop: '1px solid #1e293b',
              display: 'flex', justifyContent: 'space-between',
              fontSize: 10, color: '#334155', flexShrink: 0,
            }}>
              <span>ResQNet v1.0 · 5G-AI Disaster Response</span>
              <span>Model: XGBoost · Broker: localhost:1883</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
