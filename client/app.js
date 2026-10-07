// Screen-free client: a black page. Tap anywhere to start/stop talking.
// Sends GPS pings + recorded utterances over a websocket; plays back audio replies.
(() => {
  const statusEl = document.getElementById("status");
  const setStatus = (t) => (statusEl.textContent = t);

  let ws, started = false, recording = false, recorder, chunks = [], stream, wakeLock, audioCtx;
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
    ws.onopen = () => setStatus("ready");
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
  let lastSent = 0;
  function watchGps() {
    navigator.geolocation.watchPosition(
      (pos) => {
        const now = Date.now();
        if (now - lastSent < 8000 || !ws || ws.readyState !== 1) return;
        lastSent = now;
        ws.send(JSON.stringify({ type: "gps", lat: pos.coords.latitude, lon: pos.coords.longitude, acc: pos.coords.accuracy }));
      },
      (err) => console.warn("gps", err),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 }
    );
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
    chunks = [];
    const mime = pickMime();
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = async () => {
      const blob = new Blob(chunks, { type: recorder.mimeType });
      if (blob.size > 1500 && ws && ws.readyState === 1) ws.send(await blob.arrayBuffer());
    };
    recorder.start();
    recording = true; beep(880); navigator.vibrate && navigator.vibrate(30); setStatus("listening");
  }
  function stopRecording() {
    recorder.stop(); recording = false; beep(520); setStatus("thinking");
  }

  // ---- first tap: unlock audio, ask permissions, connect ----
  async function begin() {
    started = true;
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    player.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA="; // unlock iOS playback
    player.play().catch(() => {});
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { setStatus("mic blocked"); return; }
    try { wakeLock = await navigator.wakeLock.request("screen"); } catch (_) { /* optional */ }
    watchGps();
    connect();
  }

  document.getElementById("hit").addEventListener("click", async () => {
    if (!started) return begin();
    if (!ws || ws.readyState !== 1) return;
    recording ? stopRecording() : startRecording();
  });

  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible" && started) {
      try { wakeLock = await navigator.wakeLock.request("screen"); } catch (_) {}
    }
  });
})();
