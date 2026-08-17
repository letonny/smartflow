"use client";

import React, { useState, useEffect, useRef } from "react";

// --- Types & Interfaces ---

interface LogItem {
  id: string;
  timestamp: string;
  level: "INFO" | "DEBUG" | "WARN" | "ERROR";
  text: string;
}

interface Stats {
  traffic: { avgSpeed: number; congestion: number; count: number };
  weather: { temp: number; rain: number; visibility: number };
  incidents: { active: number; critical: number; cleared: number };
  construction: { planned: number; active: number; completed: number };
}

// --- Constants & Data Pools ---

const LOG_TEMPLATES = {
  traffic: [
    { level: "INFO" as const, text: "Received raw batch of {BATCH_SIZE} telemetry payloads from road_segments sensor grid" },
    { level: "DEBUG" as const, text: "Validation succeeded: TrafficInputSchema parsed for segment ID {SEG_ID}" },
    { level: "INFO" as const, text: "ST_Intersects spatial index join executed successfully on viewport in {TIME}ms" },
    { level: "INFO" as const, text: "Successfully loaded {BATCH_SIZE} traffic readings to table traffic_readings in {TIME_DB}ms" },
    { level: "DEBUG" as const, text: "Calculating hourly speed moving averages for segment {SEG_ID}... delta: {DELTA} km/h" },
    { level: "INFO" as const, text: "Speed readings calibrated. Active road telemetry grid healthy." },
    { level: "DEBUG" as const, text: "Inference runner completed trip duration prediction for corridor {SEG_ID} (Result: {PRED}s)" }
  ],
  weather: [
    { level: "INFO" as const, text: "Initiating weather snapshot ingestion from spatial coordinates ({LAT}, {LON})" },
    { level: "INFO" as const, text: "PostGIS GiST nearest-neighbor operator (<->) matched snapshot {UUID_SHORT}" },
    { level: "DEBUG" as const, text: "Calculated exact geodetic distance: {DIST}m utilizing geography casting ST_Distance" },
    { level: "INFO" as const, text: "Snapshot metrics processed: Temperature {TEMP}C, Rain {RAIN} mm/hr, Visibility {VIS}m" },
    { level: "DEBUG" as const, text: "Committed 1 weather snapshot record successfully to postgres in 4.2ms" },
    { level: "INFO" as const, text: "National environmental forecast channel sync validated." }
  ],
  incidents: [
    { level: "INFO" as const, text: "Polling live incidents feed. Filtering active road disruptions." },
    { level: "INFO" as const, text: "Querying active incidents intersecting current viewport (bounding box criteria met)" },
    { level: "DEBUG" as const, text: "Incident GeoJSON parsing complete: extracted 1 POINT geometry feature" },
    { level: "INFO" as const, text: "Completed incident state checks. 0 records require database cascade." }
  ],
  construction: [
    { level: "INFO" as const, text: "Ingesting raw construction zone schedules. Validating timelines." },
    { level: "DEBUG" as const, text: "ConstructionInputSchema validated successfully for project: '{PROJECT_NAME}'" },
    { level: "INFO" as const, text: "Generated ST_LineString (SRID 4326) geometry representing restricted segment lane footprint" },
    { level: "INFO" as const, text: "Successfully committed active construction status for record ID {UUID_SHORT}" },
    { level: "DEBUG" as const, text: "Updated routing detour flags for {COUNT_CONST} active work zones." }
  ]
};

const PROJECTS = [
  "I-80 Bridge Main Deck Reconstruction",
  "Broadway Avenue Gas Main Leak Repair",
  "Highway 101 North Lane Resurfacing",
  "Cesar Chavez Blvd Signal Retiming",
  "Market St Pedestrian Plaza Barrier Install"
];

export default function Home() {
  // --- State Variables ---

  // Global KPIs
  const [throughput, setThroughput] = useState<number>(24.8);
  const [memUsage, setMemUsage] = useState<number>(42.4);
  const [dbConn, setDbConn] = useState<string>("5 / 20");
  const [modeBadge, setModeBadge] = useState<string>("MOCK DEMO");
  const [systemStatus, setSystemStatus] = useState<string>("SYSTEM HEALTHY");
  const [dbState, setDbState] = useState<string>("DB: DETECTING...");
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false);
  const [backendUrl, setBackendUrl] = useState<string>("");

  // Configuration State
  const [isRunning, setIsRunning] = useState<boolean>(true);
  const [intervalSpeed, setIntervalSpeed] = useState<number>(2500);

  // Stats Counters
  const [stats, setStats] = useState<Stats>({
    traffic: { avgSpeed: 72.4, congestion: 0.28, count: 1420 },
    weather: { temp: 22.5, rain: 0.0, visibility: 10000 },
    incidents: { active: 2, critical: 0, cleared: 5 },
    construction: { planned: 3, active: 1, completed: 2 }
  });

  // Terminal Consoles Logs
  const [trafficLogs, setTrafficLogs] = useState<LogItem[]>([]);
  const [weatherLogs, setWeatherLogs] = useState<LogItem[]>([]);
  const [incidentLogs, setIncidentLogs] = useState<LogItem[]>([]);
  const [constructionLogs, setConstructionLogs] = useState<LogItem[]>([]);

  // Card Highlight Borders (Flashes)
  const [flashTraffic, setFlashTraffic] = useState<boolean>(false);
  const [flashWeather, setFlashWeather] = useState<boolean>(false);
  const [flashIncidents, setFlashIncidents] = useState<boolean>(false);
  const [flashConstruction, setFlashConstruction] = useState<boolean>(false);

  // Terminal refs for scroll-locking to bottom
  const trafficTerminalRef = useRef<HTMLDivElement>(null);
  const weatherTerminalRef = useRef<HTMLDivElement>(null);
  const incidentsTerminalRef = useRef<HTMLDivElement>(null);
  const constructionTerminalRef = useRef<HTMLDivElement>(null);

  // --- Helper Functions ---

  const generateTimestamp = (): string => {
    const d = new Date();
    return (
      d.toLocaleTimeString("en-US", { hour12: false }) +
      "." +
      String(d.getMilliseconds()).padStart(3, "0")
    );
  };

  const logToTerminal = (
    step: "traffic" | "weather" | "incidents" | "construction",
    text: string,
    level: "INFO" | "DEBUG" | "WARN" | "ERROR" = "INFO"
  ) => {
    const newLog: LogItem = {
      id: Math.random().toString(36).substr(2, 9),
      timestamp: generateTimestamp(),
      level,
      text
    };

    const updateFn = (prevLogs: LogItem[]) => {
      const updated = [...prevLogs, newLog];
      return updated.length > 60 ? updated.slice(updated.length - 60) : updated;
    };

    if (step === "traffic") setTrafficLogs(updateFn);
    else if (step === "weather") setWeatherLogs(updateFn);
    else if (step === "incidents") setIncidentLogs(updateFn);
    else if (step === "construction") setConstructionLogs(updateFn);
  };

  const clearConsole = (step: "traffic" | "weather" | "incidents" | "construction") => {
    const clearLog: LogItem = {
      id: Math.random().toString(36).substr(2, 9),
      timestamp: generateTimestamp(),
      level: "INFO",
      text: "Console buffer cleared by Administrator."
    };

    if (step === "traffic") setTrafficLogs([clearLog]);
    else if (step === "weather") setWeatherLogs([clearLog]);
    else if (step === "incidents") setIncidentLogs([clearLog]);
    else if (step === "construction") setConstructionLogs([clearLog]);
  };

  const clearAllTerminals = () => {
    clearConsole("traffic");
    clearConsole("weather");
    clearConsole("incidents");
    clearConsole("construction");
  };

  // Generate simulated logging step
  const generateSingleLog = (step: "traffic" | "weather" | "incidents" | "construction") => {
    const templates = LOG_TEMPLATES[step];
    const template = templates[Math.floor(Math.random() * templates.length)];

    let logText = template.text;

    // Token Replacements
    logText = logText.replace(/{BATCH_SIZE}/g, String(Math.floor(Math.random() * 12) + 5));
    logText = logText.replace(/{SEG_ID}/g, String(Math.floor(Math.random() * 200) + 100));
    logText = logText.replace(/{TIME}/g, (Math.random() * 12 + 2).toFixed(1));
    logText = logText.replace(/{TIME_DB}/g, (Math.random() * 8 + 1).toFixed(1));
    logText = logText.replace(/{DELTA}/g, (Math.random() * 6 - 3).toFixed(1));
    logText = logText.replace(/{PRED}/g, String(Math.floor(Math.random() * 300) + 120));
    logText = logText.replace(/{LAT}/g, (37.76 + Math.random() * 0.04).toFixed(4));
    logText = logText.replace(/{LON}/g, (-122.44 + Math.random() * 0.05).toFixed(4));
    logText = logText.replace(/{DIST}/g, String(Math.floor(Math.random() * 400) + 50));
    logText = logText.replace(/{TEMP}/g, stats.weather.temp.toFixed(1));
    logText = logText.replace(/{RAIN}/g, stats.weather.rain.toFixed(1));
    logText = logText.replace(/{VIS}/g, String(stats.weather.visibility));
    logText = logText.replace(/{PROJECT_NAME}/g, PROJECTS[Math.floor(Math.random() * PROJECTS.length)]);
    logText = logText.replace(/{COUNT_CONST}/g, String(stats.construction.active));
    logText = logText.replace(/{UUID_SHORT}/g, Math.random().toString(16).substr(2, 8));

    logToTerminal(step, logText, template.level);

    if (step === "traffic") {
      setStats((prev) => ({
        ...prev,
        traffic: { ...prev.traffic, count: prev.traffic.count + Math.floor(Math.random() * 4) + 1 }
      }));
    }
  };

  // Trigger sync button simulation
  const triggerSyncETL = () => {
    logToTerminal("traffic", "Sync action requested. Executing force pipeline updates...", "INFO");
    logToTerminal("weather", "Sync action requested. Initiating rapid sensor polling...", "INFO");
    logToTerminal("incidents", "Sync action requested. Re-indexing live GeoJSON layers...", "INFO");
    logToTerminal("construction", "Sync action requested. Refreshing dynamic workzone constraints...", "INFO");

    setTimeout(() => {
      generateSingleLog("traffic");
      generateSingleLog("weather");
      generateSingleLog("incidents");
      generateSingleLog("construction");
    }, 300);

    setTimeout(() => {
      generateSingleLog("traffic");
      generateSingleLog("weather");
      generateSingleLog("incidents");
      generateSingleLog("construction");
    }, 700);
  };

  // Scenario Triggers
  const triggerScenario = (type: "rush-hour" | "thunderstorm" | "accident" | "construction") => {
    if (type === "rush-hour") {
      setFlashTraffic(true);
      setTimeout(() => setFlashTraffic(false), 2000);

      setStats((prev) => ({
        ...prev,
        traffic: { avgSpeed: 22.4, congestion: 0.88, count: prev.traffic.count + 8 }
      }));

      logToTerminal("traffic", "ALERT: Severe congestion detected on Segment ID 112 (Central Expressway North)", "WARN");
      logToTerminal("traffic", "Traffic Dynamics moving average calculations drop below 25 km/h limit.", "WARN");
      logToTerminal("traffic", "SQL query lateral join flagged slow execution time (342ms) due to scale.", "DEBUG");
      logToTerminal("traffic", "ALERT: High load threshold reached for traffic_readings index. Partitioning recommended.", "WARN");
      logToTerminal("traffic", "Successfully updated congestion routing profiles for 11 downstream routes.", "INFO");
    } else if (type === "thunderstorm") {
      setFlashWeather(true);
      setTimeout(() => setFlashWeather(false), 2000);

      setStats((prev) => ({
        ...prev,
        weather: { ...prev.weather, rain: 19.5, temp: 13.8, visibility: 1200 }
      }));

      logToTerminal("weather", "ALERT: Precipitation surge detected. Continuous rain intensity > 18 mm/hr", "WARN");
      logToTerminal("weather", "Atmospheric visibility drop: degrading from 10,000m to 1,200m (Advisory Status: Severe)", "WARN");
      logToTerminal("weather", "Spatial nearest-neighbor queries recalculating grid distances with weather profiles.", "INFO");
      logToTerminal("weather", "ERROR: Heavy noise feedback on ambient thermometer channel WS-14.", "ERROR");
      logToTerminal("weather", "Successfully committed degraded weather profile for routing optimization matrix.", "INFO");
    } else if (type === "accident") {
      setFlashIncidents(true);
      setTimeout(() => setFlashIncidents(false), 2000);

      setStats((prev) => ({
        ...prev,
        incidents: { ...prev.incidents, active: prev.incidents.active + 1, critical: prev.incidents.critical + 1 }
      }));

      logToTerminal("incidents", "CRITICAL INGESTION: Multi-vehicle accident reported on Segment 108 (Bay Bridge Eastbound)", "ERROR");
      logToTerminal("incidents", "Validation succeeded: Ingested GeoJSON POINT geometry (SRID 4326)", "INFO");
      logToTerminal("incidents", "DB execution: Inserted incident row UUID " + Math.random().toString(16).substr(2, 8) + " successfully.", "INFO");
      logToTerminal("incidents", "ALERT: Critical event on corridor triggers automatic ML routing time recalculations.", "WARN");
    } else if (type === "construction") {
      setFlashConstruction(true);
      setTimeout(() => setFlashConstruction(false), 2000);

      setStats((prev) => ({
        ...prev,
        construction: {
          ...prev.construction,
          active: prev.construction.active + 1,
          planned: Math.max(0, prev.construction.planned - 1)
        }
      }));

      logToTerminal("construction", "INGEST: Scheduled lane restriction transitioned from 'planned' to 'active'.", "INFO");
      logToTerminal("construction", "Project: 'I-80 Bridge Main Deck Reconstruction'. Segment restriction ID 405.", "INFO");
      logToTerminal("construction", "ST_Polygon geometry loaded. Restricted lane capacity updated to 50% flow capacity.", "WARN");
      logToTerminal("construction", "Successfully completed index update for active work zones.", "INFO");
    }
  };

  // --- Live Backend Syncing ---

  const checkBackendConnection = async () => {
    // Attempt standard health routes through proxy or absolute URL fallback
    const endpoints = ["/api/health", "http://127.0.0.1:8000/api/health"];
    let connected = false;

    for (const url of endpoints) {
      try {
        const response = await fetch(url, { method: "GET" });
        if (response.ok) {
          const data = await response.json();
          connected = true;
          setIsLiveBackend(true);
          setBackendUrl(url.replace("/api/health", ""));

          const dbHealthy =
            data.services?.database?.status === "healthy";
          setDbState(
            dbHealthy ? "DB: POSTGRESQL CONNECTED" : "DB: POSTGRES DEGRADED"
          );

          setModeBadge("LIVE BACKEND");
          if (data.status === "online") {
            setSystemStatus("API CONTEXT: ONLINE");
            logToTerminal(
              "traffic",
              `Successfully bound connection to Live FastAPI server at ${url.replace("/api/health", "")}`,
              "INFO"
            );
            fetchLiveCounts(url.replace("/api/health", ""));
          } else {
            setSystemStatus("API CONTEXT: DEGRADED");
            logToTerminal(
              "traffic",
              "Connection to API succeeded, but database services report degraded state.",
              "WARN"
            );
          }
          break;
        }
      } catch (e) {
        // Continue fallback attempts
      }
    }

    if (!connected) {
      setIsLiveBackend(false);
      setModeBadge("MOCK DEMO");
      setSystemStatus("SYSTEM HEALTHY");
      setDbState("DB: DISCONNECTED (DEMO)");
      logToTerminal(
        "traffic",
        "FastAPI backend offline or inaccessible. Running in high-fidelity mock stream mode.",
        "INFO"
      );
    }
  };

  const fetchLiveCounts = async (url: string) => {
    try {
      const response = await fetch(`${url}/api/incidents`);
      if (response.ok) {
        const data = await response.json();
        if (data.features) {
          setStats((prev) => ({
            ...prev,
            incidents: { ...prev.incidents, active: data.features.length }
          }));
          logToTerminal(
            "incidents",
            `Successfully queried ${data.features.length} active incidents from Live DB.`,
            "INFO"
          );
        }
      }
    } catch (e) {
      // Silently fall back
    }
  };

  // --- React Lifecycle Effects ---

  // Initialization & Connections
  useEffect(() => {
    // Initial logs
    logToTerminal("traffic", "SmartFlow Traffic Ingestion pipeline online.", "INFO");
    logToTerminal("traffic", "Awaiting telemetry data packet streams...", "DEBUG");

    logToTerminal("weather", "Weather Alert Ingestion pipeline online.", "INFO");
    logToTerminal("weather", "Listening for spatial coordinates snapshot updates...", "DEBUG");

    logToTerminal("incidents", "Active Road Incidents GeoJSON processor online.", "INFO");
    logToTerminal("incidents", "Awaiting incident report events...", "DEBUG");

    logToTerminal("construction", "Construction Zone schedule synchronizer online.", "INFO");
    logToTerminal("construction", "Ready to load planned/active restricted lanes...", "DEBUG");

    // Populate rapid initial mock logs
    for (let i = 0; i < 4; i++) {
      setTimeout(() => generateSingleLog("traffic"), 100 * i);
      setTimeout(() => generateSingleLog("weather"), 150 * i);
      setTimeout(() => generateSingleLog("incidents"), 200 * i);
      setTimeout(() => generateSingleLog("construction"), 250 * i);
    }

    // Connect to real FastAPI backend
    checkBackendConnection();
  }, []);

  // Live streaming ticker
  useEffect(() => {
    if (!isRunning) return;

    const timer = setInterval(() => {
      // Fluctuate global headers
      setThroughput(
        (prev) => Math.round((24.8 + (Math.random() - 0.5) * 4) * 10) / 10
      );
      setMemUsage(
        (prev) => Math.round((42.4 + (Math.random() - 0.5) * 1.5) * 10) / 10
      );

      // Choose random terminal to receive a log
      const steps = ["traffic", "weather", "incidents", "construction"] as const;
      const chosen = steps[Math.floor(Math.random() * steps.length)];
      generateSingleLog(chosen);

      // Fluctuate stats
      setStats((prev) => {
        const speedDrift = (Math.random() - 0.5) * 0.8;
        const newSpeed = Math.round(Math.max(50, Math.min(85, prev.traffic.avgSpeed + speedDrift)) * 10) / 10;

        const congestDrift = (Math.random() - 0.5) * 0.02;
        const newCongest = Math.round(Math.max(0.05, Math.min(0.95, prev.traffic.congestion + congestDrift)) * 100) / 100;

        const tempDrift = (Math.random() - 0.5) * 0.1;
        const newTemp = Math.round(Math.max(12, Math.min(32, prev.weather.temp + tempDrift)) * 10) / 10;

        return {
          ...prev,
          traffic: { ...prev.traffic, avgSpeed: newSpeed, congestion: newCongest },
          weather: { ...prev.weather, temp: newTemp }
        };
      });
    }, intervalSpeed);

    return () => clearInterval(timer);
  }, [isRunning, intervalSpeed, stats]);

  // Scroll locking for each terminal console
  useEffect(() => {
    if (trafficTerminalRef.current) {
      trafficTerminalRef.current.scrollTop = trafficTerminalRef.current.scrollHeight;
    }
  }, [trafficLogs]);

  useEffect(() => {
    if (weatherTerminalRef.current) {
      weatherTerminalRef.current.scrollTop = weatherTerminalRef.current.scrollHeight;
    }
  }, [weatherLogs]);

  useEffect(() => {
    if (incidentsTerminalRef.current) {
      incidentsTerminalRef.current.scrollTop = incidentsTerminalRef.current.scrollHeight;
    }
  }, [incidentLogs]);

  useEffect(() => {
    if (constructionTerminalRef.current) {
      constructionTerminalRef.current.scrollTop = constructionTerminalRef.current.scrollHeight;
    }
  }, [constructionLogs]);

  // --- Rendering Utility Helpers ---

  const getCongestionLevel = (congestion: number) => {
    if (congestion < 0.35) {
      return { text: "LIGHT", class: "text-emerald-400 bg-emerald-950/80 border-emerald-800/50" };
    } else if (congestion < 0.65) {
      return { text: "MODERATE", class: "text-amber-400 bg-amber-950/80 border-amber-800/50" };
    } else {
      return { text: "HEAVY", class: "text-red-400 bg-red-950/80 border-red-800/50" };
    }
  };

  const getLogItemStyle = (level: LogItem["level"]) => {
    switch (level) {
      case "DEBUG":
        return "text-slate-400 font-normal";
      case "WARN":
        return "text-amber-400 font-semibold";
      case "ERROR":
        return "text-red-500 font-bold animate-pulse";
      default:
        return "text-emerald-400";
    }
  };

  const renderLogBox = (logs: LogItem[], ref: React.RefObject<HTMLDivElement | null>, key: string) => (
    <div className="scanlines rounded-xl border border-slate-900 bg-black shadow-inner relative flex-1">
      <div
        ref={ref}
        className="custom-scrollbar font-mono text-xs overflow-y-auto h-52 space-y-1 p-3 select-all leading-relaxed relative z-10"
      >
        {logs.map((log) => (
          <div
            key={log.id}
            className="flex items-start font-mono text-[11px] tracking-tight py-0.5 border-b border-slate-900/40 pb-1"
          >
            <span className="text-slate-600 mr-2 select-none shrink-0">
              [{log.timestamp}]
            </span>
            <span className={`${getLogItemStyle(log.level)} mr-2 shrink-0 select-none`}>
              [{log.level}]
            </span>
            <span className="text-slate-300 break-all select-all">
              {log.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen text-slate-100 bg-slate-950 bg-grid selection:bg-cyan-500 selection:text-slate-950 flex flex-col antialiased font-sans">
      
      {/* TOP HEADER BAR */}
      <header className="border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-md px-6 py-4 shrink-0 relative z-20">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          
          {/* Branding & Logo */}
          <div className="flex items-center space-x-3.5">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-900/20">
              <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-300 bg-clip-text text-transparent">
                SmartFlow
              </h1>
              <p className="text-xs font-semibold text-slate-400 tracking-wider uppercase">Pipeline Monitoring Control</p>
            </div>
          </div>

          {/* Global Live KPI Mini Widgets */}
          <div className="hidden xl:flex items-center space-x-8 text-xs border-l border-slate-800 pl-8">
            <div>
              <div className="text-slate-500 mb-0.5">Global Throughput</div>
              <div className="font-mono font-medium text-slate-200 flex items-center">
                <span>{throughput.toFixed(1)}</span>
                <span class="text-slate-500 ml-1">rec/s</span>
              </div>
            </div>
            <div>
              <div className="text-slate-500 mb-0.5">DB Connections</div>
              <div className="font-mono font-medium text-slate-200">
                <span>{dbConn}</span>
                <span class="text-cyan-500 ml-1">Active</span>
              </div>
            </div>
            <div>
              <div className="text-slate-500 mb-0.5">Memory Usage</div>
              <div className="font-mono font-medium text-slate-200">
                <span>{memUsage.toFixed(1)}</span>
                <span class="text-slate-500 ml-1">MB</span>
              </div>
            </div>
          </div>

          {/* Global System Status Indicators */}
          <div className="flex items-center space-x-4 self-end md:self-auto">
            {/* Sync Indicator */}
            <div className="flex items-center bg-slate-900/90 border border-slate-800 rounded-lg px-3 py-1.5 text-xs">
              <span className="text-slate-400 font-medium mr-2">Status Mode:</span>
              <span className={`font-bold tracking-wide ${isLiveBackend ? "text-emerald-400" : "text-cyan-400"}`}>
                {modeBadge}
              </span>
            </div>
            
            {/* Main Connection Light */}
            <div className="flex items-center bg-slate-900/90 border border-slate-800 rounded-lg px-3 py-1.5 text-xs space-x-2">
              <div className={`h-2.5 w-2.5 rounded-full glowing-dot-active shadow-[0_0_10px] ${isLiveBackend ? "bg-emerald-500 shadow-emerald-500/80" : "bg-emerald-500 shadow-emerald-500/80"}`} />
              <span className="font-semibold text-slate-200 tracking-wide">
                {systemStatus}
              </span>
            </div>
          </div>

        </div>
      </header>

      {/* MAIN DASHBOARD CONTENT */}
      <main className="flex-1 overflow-y-auto p-6 max-w-7xl w-full mx-auto space-y-6">

        {/* WORKSPACE OVERVIEW */}
        <div className="bg-gradient-to-r from-slate-900/80 to-slate-900/40 border border-slate-800/60 rounded-2xl p-6 shadow-xl backdrop-blur-md relative overflow-hidden">
          <div className="absolute top-0 right-0 h-40 w-40 bg-gradient-to-bl from-indigo-500/5 to-cyan-500/5 rounded-full filter blur-xl" />
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2 font-sans">
                <span>PostGIS Spatial Intelligence Orchestrator</span>
                <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono font-normal">v1.0.0-beta</span>
              </h2>
              <p className="text-sm text-slate-400 mt-1 max-w-2xl font-sans">
                This administrative panel tracks continuous spatial streaming loads for the SmartFlow core server. Ingested datasets are parsed, georeferenced via geometry castings, and committed directly to Supabase PostGIS spatial indices.
              </p>
            </div>
            <div className="shrink-0 flex gap-2">
              <button
                onClick={triggerSyncETL}
                className="px-4 py-2 bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 active:scale-95 transition-all text-xs font-semibold rounded-lg shadow-md shadow-cyan-950/20 flex items-center space-x-2"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.253 8H18" />
                </svg>
                <span>Force Ingestion Sync</span>
              </button>
              <button
                onClick={clearAllTerminals}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 active:scale-95 transition-all text-xs font-semibold rounded-lg text-slate-300"
              >
                Clear Consoles
              </button>
            </div>
          </div>
        </div>

        {/* COGNITIVE CARDS GRID */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* CARD 1: TRAFFIC TELEMETRY */}
          <div
            className={`group bg-slate-900/50 border transition-all duration-300 rounded-2xl p-5 shadow-2xl flex flex-col relative overflow-hidden ${flashTraffic ? "border-cyan-500 ring-2 ring-cyan-500/20" : "border-slate-800 hover:border-slate-700/80"}`}
          >
            <div className="absolute top-0 right-0 h-24 w-24 bg-gradient-to-bl from-cyan-500/5 to-transparent rounded-bl-3xl pointer-events-none" />
            
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800/60">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 rounded-xl bg-cyan-950/50 border border-cyan-800/40 text-cyan-400">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-bold text-slate-100 group-hover:text-cyan-400 transition-colors">Traffic Dynamics</h3>
                  <p className="text-[10px] text-slate-400 font-mono">STEP 1 • TELEMETRY INGEST</p>
                </div>
              </div>
              <span className="text-[10px] bg-cyan-950/60 text-cyan-400 border border-cyan-800/40 px-2 py-0.5 rounded-full font-mono font-medium">14.2 req/s</span>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Avg Network Speed</span>
                <span className="font-mono text-lg font-bold text-cyan-400">
                  {stats.traffic.avgSpeed.toFixed(1)} <span className="text-xs text-slate-500 font-normal">km/h</span>
                </span>
              </div>
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Congestion Index</span>
                <div className="flex items-center justify-center space-x-1.5">
                  <span className="font-mono text-lg font-bold text-slate-200">
                    {stats.traffic.congestion.toFixed(2)}
                  </span>
                  <span className={`text-[9px] px-1 rounded border font-sans font-semibold ${getCongestionLevel(stats.traffic.congestion).class}`}>
                    {getCongestionLevel(stats.traffic.congestion).text}
                  </span>
                </div>
              </div>
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Processed Telemetry</span>
                <span className="font-mono text-lg font-bold text-slate-300">
                  {stats.traffic.count.toLocaleString()}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between text-[11px] mb-1.5 px-1 text-slate-500 font-medium">
              <span className="font-mono flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                ST_Intersects Segment Join Stream
              </span>
              <button onClick={() => clearConsole("traffic")} className="hover:text-slate-300 transition-colors font-mono">CLEAR</button>
            </div>

            {renderLogBox(trafficLogs, trafficTerminalRef, "traffic")}
          </div>

          {/* CARD 2: WEATHER ALERT FEED */}
          <div
            className={`group bg-slate-900/50 border transition-all duration-300 rounded-2xl p-5 shadow-2xl flex flex-col relative overflow-hidden ${flashWeather ? "border-amber-500 ring-2 ring-amber-500/20" : "border-slate-800 hover:border-slate-700/80"}`}
          >
            <div className="absolute top-0 right-0 h-24 w-24 bg-gradient-to-bl from-amber-500/5 to-transparent rounded-bl-3xl pointer-events-none" />
            
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800/60">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 rounded-xl bg-amber-950/50 border border-amber-800/40 text-amber-400">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-bold text-slate-100 group-hover:text-amber-400 transition-colors">Weather Alerts</h3>
                  <p className="text-[10px] text-slate-400 font-mono">STEP 2 • ENVIRONMENT TRACKER</p>
                </div>
              </div>
              <span className="text-[10px] bg-amber-950/60 text-amber-400 border border-amber-800/40 px-2 py-0.5 rounded-full font-mono font-medium">1.0 req/s</span>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Temperature</span>
                <span className="font-mono text-lg font-bold text-amber-400">
                  {stats.weather.temp.toFixed(1)} <span className="text-xs text-slate-500 font-normal">°C</span>
                </span>
              </div>
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Rain Intensity</span>
                <span className="font-mono text-lg font-bold text-slate-200">
                  {stats.weather.rain.toFixed(1)} <span className="text-xs text-slate-500 font-normal">mm/h</span>
                </span>
              </div>
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Visibility Range</span>
                <span className="font-mono text-lg font-bold text-slate-300">
                  {stats.weather.visibility.toLocaleString()} <span className="text-xs text-slate-500 font-normal">m</span>
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between text-[11px] mb-1.5 px-1 text-slate-500 font-medium">
              <span className="font-mono flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-ping" />
                PostGIS Spatial KNN Snapshot Stream
              </span>
              <button onClick={() => clearConsole("weather")} className="hover:text-slate-300 transition-colors font-mono">CLEAR</button>
            </div>

            {renderLogBox(weatherLogs, weatherTerminalRef, "weather")}
          </div>

          {/* CARD 3: ACTIVE ROAD INCIDENTS */}
          <div
            className={`group bg-slate-900/50 border transition-all duration-300 rounded-2xl p-5 shadow-2xl flex flex-col relative overflow-hidden ${flashIncidents ? "border-red-500 ring-2 ring-red-500/20" : "border-slate-800 hover:border-slate-700/80"}`}
          >
            <div className="absolute top-0 right-0 h-24 w-24 bg-gradient-to-bl from-red-500/5 to-transparent rounded-bl-3xl pointer-events-none" />
            
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800/60">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 rounded-xl bg-red-950/50 border border-red-800/40 text-red-400">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-bold text-slate-100 group-hover:text-red-400 transition-colors">Active Incidents</h3>
                  <p className="text-[10px] text-slate-400 font-mono">STEP 3 • ROAD DISRUPTIONS</p>
                </div>
              </div>
              <span className="text-[10px] bg-red-950/60 text-red-400 border border-red-800/40 px-2 py-0.5 rounded-full font-mono font-medium">0.2 req/s</span>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Active Blocks</span>
                <span className="font-mono text-lg font-bold text-red-400">
                  {stats.incidents.active} <span className="text-xs text-slate-500 font-normal">Events</span>
                </span>
              </div>
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Critical Priority</span>
                <span className="font-mono text-lg font-bold text-slate-200">
                  {stats.incidents.critical}
                </span>
              </div>
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Cleared (1 Hour)</span>
                <span className="font-mono text-lg font-bold text-slate-300">
                  {stats.incidents.cleared}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between text-[11px] mb-1.5 px-1 text-slate-500 font-medium">
              <span className="font-mono flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-red-400 animate-ping" />
                Point GeoJSON Live Ingestion Stream
              </span>
              <button onClick={() => clearConsole("incidents")} className="hover:text-slate-300 transition-colors font-mono">CLEAR</button>
            </div>

            {renderLogBox(incidentLogs, incidentsTerminalRef, "incidents")}
          </div>

          {/* CARD 4: CONSTRUCTION LANE RESTRICTIONS */}
          <div
            className={`group bg-slate-900/50 border transition-all duration-300 rounded-2xl p-5 shadow-2xl flex flex-col relative overflow-hidden ${flashConstruction ? "border-emerald-500 ring-2 ring-emerald-500/20" : "border-slate-800 hover:border-slate-700/80"}`}
          >
            <div className="absolute top-0 right-0 h-24 w-24 bg-gradient-to-bl from-emerald-500/5 to-transparent rounded-bl-3xl pointer-events-none" />
            
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800/60">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 rounded-xl bg-emerald-950/50 border border-emerald-800/40 text-emerald-400">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-bold text-slate-100 group-hover:text-emerald-400 transition-colors">Construction Zones</h3>
                  <p className="text-[10px] text-slate-400 font-mono">STEP 4 • LANE RESTRICTIONS</p>
                </div>
              </div>
              <span className="text-[10px] bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 px-2 py-0.5 rounded-full font-mono font-medium">0.1 req/s</span>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Planned Zones</span>
                <span className="font-mono text-lg font-bold text-slate-300">
                  {stats.construction.planned}
                </span>
              </div>
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Active Restrictions</span>
                <span className="font-mono text-lg font-bold text-emerald-400">
                  {stats.construction.active} <span className="text-xs text-slate-500 font-normal">Zone</span>
                </span>
              </div>
              <div className="bg-slate-950/55 rounded-xl p-3 border border-slate-800/30 text-center">
                <span class="text-[10px] text-slate-500 block mb-1">Completed Today</span>
                <span className="font-mono text-lg font-bold text-slate-400">
                  {stats.construction.completed}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between text-[11px] mb-1.5 px-1 text-slate-500 font-medium">
              <span className="font-mono flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
                Polygon & LineString Loader Feed
              </span>
              <button onClick={() => clearConsole("construction")} className="hover:text-slate-300 transition-colors font-mono">CLEAR</button>
            </div>

            {renderLogBox(constructionLogs, constructionTerminalRef, "construction")}
          </div>

        </div>

        {/* BOTTOM INTERACTIVE PRESENTATION CONTROLLER */}
        <div className="bg-gradient-to-r from-slate-900 to-slate-900/60 border border-slate-800 rounded-2xl p-6 shadow-2xl relative">
          <div className="flex flex-col xl:flex-row items-start xl:items-center justify-between gap-6">
            
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2 font-sans">
                <span className="h-2.5 w-2.5 rounded bg-cyan-500 animate-pulse" />
                Interactive Live Presentation Controller
              </h3>
              <p className="text-xs text-slate-400 font-sans">
                Deploy events instantly during live demonstrations to dynamically trigger custom pipeline warning sequences, error traps, and statistical fluctuations.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-4 bg-slate-950/50 p-3 rounded-xl border border-slate-800/60 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-400 font-sans">Stream Status:</span>
                <button
                  onClick={() => {
                    setIsRunning(!isRunning);
                    logToTerminal(
                      "traffic",
                      isRunning ? "Simulated stream feeds suspended by user." : "Simulated stream feeds resumed.",
                      isRunning ? "WARN" : "INFO"
                    );
                  }}
                  className={`px-2.5 py-1 rounded font-semibold transition-all ${isRunning ? "bg-cyan-600 hover:bg-cyan-500" : "bg-slate-800 hover:bg-slate-700 text-slate-400"}`}
                >
                  {isRunning ? "RUNNING" : "PAUSED"}
                </button>
              </div>
              <div className="h-4 w-px bg-slate-800" />
              <div className="flex items-center gap-2">
                <span className="text-slate-400 font-sans">Sync Interval:</span>
                <select
                  value={intervalSpeed}
                  onChange={(e) => {
                    const newSpeed = parseInt(e.target.value);
                    setIntervalSpeed(newSpeed);
                    logToTerminal("traffic", `Stream pacing interval updated to ${newSpeed}ms.`, "DEBUG");
                  }}
                  className="bg-slate-900 border border-slate-700 rounded px-2 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none text-slate-200 font-sans"
                >
                  <option value={1000}>Fast (1.0s)</option>
                  <option value={2500}>Standard (2.5s)</option>
                  <option value={5000}>Slow (5.0s)</option>
                  <option value={10000}>Stretched (10s)</option>
                </select>
              </div>
            </div>

            <div className="flex flex-wrap gap-2.5">
              <button
                onClick={() => triggerScenario("rush-hour")}
                className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 hover:text-cyan-400 transition-all text-xs font-semibold rounded-lg border border-slate-700/60 flex items-center space-x-1.5"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
                <span className="font-sans">Rush Hour</span>
              </button>
              <button
                onClick={() => triggerScenario("thunderstorm")}
                className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 hover:text-amber-400 transition-all text-xs font-semibold rounded-lg border border-slate-700/60 flex items-center space-x-1.5"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                <span className="font-sans">Rainstorm</span>
              </button>
              <button
                onClick={() => triggerScenario("accident")}
                className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 hover:text-red-400 transition-all text-xs font-semibold rounded-lg border border-slate-700/60 flex items-center space-x-1.5"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                <span className="font-sans">Crash Event</span>
              </button>
              <button
                onClick={() => triggerScenario("construction")}
                className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 hover:text-emerald-400 transition-all text-xs font-semibold rounded-lg border border-slate-700/60 flex items-center space-x-1.5"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                <span className="font-sans">Lane Closure</span>
              </button>
            </div>

          </div>
        </div>

      </main>

      {/* FOOTER */}
      <footer className="border-t border-slate-800/80 bg-slate-900/20 px-6 py-3.5 shrink-0 text-center text-xs text-slate-500 relative z-20">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-2">
          <div className="font-sans">
            © 2026 SmartFlow Analytics Grid. Built for live deployment and presentation.
          </div>
          <div className="font-mono text-[10px] text-slate-600 flex items-center justify-center gap-3">
            <span>POSTGIS: 3.4 ACTIVE</span>
            <span className="h-3 w-px bg-slate-800" />
            <span>FASTAPI: COMPATIBLE</span>
            <span className="h-3 w-px bg-slate-800" />
            <span>{dbState}</span>
          </div>
        </div>
      </footer>

    </div>
  );
}
