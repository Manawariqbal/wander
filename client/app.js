// Screen-free client: a black page. Tap once to talk; it stops listening when you stop talking.
// Sends GPS pings + recorded utterances over a websocket; plays back audio replies.
(() => {
  const statusEl = document.getElementById("status");
  const setStatus = (t) => (statusEl.textContent = t);

  // ---- debugging: set to false once everything works ----
  const DEBUG = false;  // plays back your recording + logs mic levels in the console

  // ---- end-of-speech tuning ----
  const SILENCE_MS = 1200;      // quiet this long after speech => stop
  const NO_SPEECH_MS = 7000;    // never spoke => cancel
  const MAX_MS = 20000;         // hard cap per utterance
  const START_DELAY_MS = 350;   // ignore the start beep
  const MIN_VOICE_MS = 250;     // need this much voice to count as speech
  const MIN_THRESHOLD = 0.012;  // raise if background noise keeps it listening

  let ws, started = false, recording = false, recorder, chunks = [], stream, wakeLock, audioCtx, analyser;
  let vadTimer = null, discard = false;
  let pendingHeader = null;
  const queue = [];
  const player = new Audio();
  let playing = false;

  // ---- audio cues so you never need to look at the screen ----
  function beep(freq, ms = 90) {
    if (!audioCtx) return;
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.frequency.value = freq; g.gain.value = 0.08;
    o.connect(g); g.connect(audioCtx.destination);
    o.start(); o.stop(audioCtx.currentTime + ms / 1000);
  }

  // ---- playback queue ----
  function playNext() {
    if (playing || queue.length === 0) return;
    playing = true;
    player.src = queue.shift();
    player.onended = () => { playing = false; playNext(); };
    player.onerror = () => { playing = false; playNext(); };
    player.play().catch(() => { playing = false; });
  }
  function stopPlayback() {
    queue.length = 0; player.pause(); playing = false;
  }

  // ---- websocket ----
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/walk`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => { setStatus("ready"); sendGps(); };
    ws.onclose = () => { setStatus("reconnecting"); setTimeout(connect, 2000); };
    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        const m = JSON.parse(ev.data);
        if (m.type === "audio") pendingHeader = m;
        else if (m.type === "stop") stopPlayback();
        else if (m.type === "status") setStatus(m.state);
        else if (m.type === "transcript") console.log("heard:", m.text);
      } else if (pendingHeader) {
        const blob = new Blob([ev.data], { type: pendingHeader.mime });
        queue.push(URL.createObjectURL(blob));
        pendingHeader = null;
        setStatus("speaking");
        playNext();
      }
    };
  }

  // ---- GPS ----
    // ---- GPS ----
  const gpsEl = document.createElement("div");
  gpsEl.style.cssText =
    "position:fixed;top:0;left:0;right:0;text-align:center;pointer-events:none;" +
    "padding:calc(env(safe-area-inset-top,0px) + 10px) 12px 0;" +
    "font:13px system-ui,sans-serif;color:#0e3c1e";
  document.body.appendChild(gpsEl);
  const setGps = (t) => { gpsEl.textContent = t; };

  let lastPos = null;
  function sendGps() {
    if (!lastPos || !ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify({ type: "gps", lat: lastPos.latitude, lon: lastPos.longitude, acc: lastPos.accuracy }));
  }
  function onFix(pos) {
    const first = !lastPos;
    lastPos = pos.coords;
    setGps(`GPS ok (±${Math.round(pos.coords.accuracy)} m)`);
    if (first) sendGps();
  }
  function onGpsError(err) {
    const msg = {
      1: "GPS blocked: allow Location for this site in your browser settings",
      2: "GPS unavailable: turn on Location in your phone settings, then go outside",
      3: "GPS timed out: still trying",
    }[err.code] || "GPS error";
    setGps(msg);
    console.warn("gps", err);
  }
  function watchGps() {
    if (!("geolocation" in navigator)) { setGps("This browser has no GPS support"); return; }
    setGps("GPS: waiting for a fix...");
    // quick coarse fix (Wi-Fi / cell) first, then precise updates
    navigator.geolocation.getCurrentPosition(onFix, onGpsError,
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 120000 });
    navigator.geolocation.watchPosition(onFix, onGpsError,
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 30000 });
    setInterval(sendGps, 8000);  // keep pinging even when the position doesn't change
  }

  // ---- voice activity detection (simple energy-based) ----
  function startVad() {
    const buf = new Float32Array(analyser.fftSize);
    const t0 = performance.now();
    let last = t0, noise = 0.003, voiceMs = 0, lastVoice = 0, speechStarted = false, peak = 0, ticks = 0;

    vadTimer = setInterval(() => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      const now = performance.now(), dt = now - last, elapsed = now - t0;
      last = now;
      if (elapsed < START_DELAY_MS) return;

      peak = Math.max(peak, rms);
      const threshold = Math.max(MIN_THRESHOLD, noise * 3);
      if (DEBUG && ++ticks % 10 === 0) {
        console.log(`mic rms=${rms.toFixed(4)} threshold=${threshold.toFixed(4)} speech=${speechStarted}`);
      }

      if (rms > threshold) {
        voiceMs += dt; lastVoice = now;
        if (voiceMs >= MIN_VOICE_MS) speechStarted = true;
      } else if (!speechStarted) {
        noise = 0.95 * noise + 0.05 * rms; // track background level
      }

      if (speechStarted && now - lastVoice > SILENCE_MS) finish(false);
      else if (!speechStarted && elapsed > NO_SPEECH_MS) {
        if (DEBUG) console.warn(`no speech detected. loudest level seen: ${peak.toFixed(4)} (threshold ${threshold.toFixed(4)})`);
        finish(true);
      }
      else if (elapsed > MAX_MS) finish(false);
    }, 50);
  }

  function finish(cancel) {
    if (!recording) return;
    clearInterval(vadTimer); vadTimer = null;
    discard = cancel;
    recorder.stop();
    recording = false;
    beep(520);
    setStatus(cancel ? "ready" : "thinking");
  }

  // ---- recording ----
  function pickMime() {
    for (const m of ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"]) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) return m;
    }
    return "";
  }
  function startRecording() {
    stopPlayback();
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "interrupt" }));
    chunks = []; discard = false;
    const mime = pickMime();
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = async () => {
      if (discard) return;
      const blob = new Blob(chunks, { type: recorder.mimeType });
      console.log("recorded bytes:", blob.size, blob.type);
      if (DEBUG) new Audio(URL.createObjectURL(blob)).play().catch(() => {}); // hear what was captured
      if (blob.size > 1500 && ws && ws.readyState === 1) ws.send(await blob.arrayBuffer());
      else setStatus("ready");
    };
    recorder.start();
    recording = true; beep(880); navigator.vibrate && navigator.vibrate(30); setStatus("listening");
    startVad();
  }

  // ---- first tap: unlock audio, ask permissions, connect ----
  async function begin() {
    started = true;
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    player.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA="; // unlock iOS playback
    player.play().catch(() => {});
    try {
      // Raw microphone signal: browser processing can pump noise and hurt Whisper.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
    } catch (e) { setStatus("mic blocked"); return; }

    if (DEBUG) {
      const t = stream.getAudioTracks()[0];
      console.log("microphone in use:", t.label, t.getSettings());
    }

    // analyser for end-of-speech detection (not connected to speakers)
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    audioCtx.createMediaStreamSource(stream).connect(analyser);

    try { wakeLock = await navigator.wakeLock.request("screen"); } catch (_) { /* optional */ }
    watchGps();
    connect();
  }

  document.getElementById("hit").addEventListener("click", async () => {
    if (!started) return begin();
    if (!ws || ws.readyState !== 1) return;
    if (audioCtx && audioCtx.state === "suspended") await audioCtx.resume();
    recording ? finish(false) : startRecording();  // tap again to stop early
  });

  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible" && started) {
      try { wakeLock = await navigator.wakeLock.request("screen"); } catch (_) {}
    }
  });
})();