// Lesson player: one video at a time per account, resume, progress, auto-next, watermark.
(function () {
  var v = document.getElementById("player");
  if (!v) return;
  var d = v.dataset, lastSent = 0, sending = false;
  var stage = document.getElementById("stage");
  var box = document.getElementById("elsewhere");
  var auto = document.getElementById("autonext");
  var H = {"Content-Type": "application/json", "X-CSRF-Token": d.csrf};

  try { if (localStorage.getItem("autonext") === "0") auto.checked = false; } catch (e) {}
  auto.addEventListener("change", function () {
    try { localStorage.setItem("autonext", auto.checked ? "1" : "0"); } catch (e) {}
  });

  // --- one video at a time ------------------------------------------------------
  function blocked(device) {
    v.pause();
    document.getElementById("elsewhere-device").textContent = device ? "(" + device + ")" : "";
    box.hidden = false;
  }
  function load() {          // attach the video only once this device may play
    if (!v.getAttribute("src")) { v.src = d.src; }
  }
  function claim(takeover) {
    return fetch("/api/play", {method: "POST", credentials: "same-origin", headers: H,
                               body: JSON.stringify({takeover: !!takeover})})
      .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, j: j}; }); });
  }
  fetch("/api/play", {credentials: "same-origin"}).then(function (r) { return r.json(); })
    .then(function (j) { if (j.elsewhere) blocked(j.elsewhere); else load(); })
    .catch(load);
  document.getElementById("takeover").addEventListener("click", function () {
    claim(true).then(function (res) {
      if (!res.ok) return;
      box.hidden = true;
      var t = v.currentTime;
      if (!v.getAttribute("src")) load(); else { v.load(); v.currentTime = t; }
      v.play().catch(function () {});
    });
  });
  v.addEventListener("play", function () {
    claim(false).then(function (res) { if (!res.ok && res.j.error === "elsewhere") blocked(res.j.device); });
  });
  v.addEventListener("error", function () {   // e.g. 409: another device started meanwhile
    fetch("/api/play", {credentials: "same-origin"}).then(function (r) { return r.json(); })
      .then(function (j) { if (j.elsewhere) blocked(j.elsewhere); });
  });

  // --- resume and progress ------------------------------------------------------
  v.addEventListener("loadedmetadata", function () {
    var start = parseFloat(d.start || "0");
    if (start > 5 && start < v.duration - 5) v.currentTime = start;
  });
  v.addEventListener("contextmenu", function (e) { e.preventDefault(); });

  function send(ended, beacon) {
    if (!v.duration || sending) return;
    var body = JSON.stringify({course: d.course, lesson: d.lesson, position: v.currentTime,
                               duration: v.duration, ended: !!ended, playing: !v.paused && !ended});
    lastSent = Date.now();
    if (beacon) {   // page is closing: fire and forget
      fetch("/api/progress", {method: "POST", body: body, keepalive: true, credentials: "same-origin", headers: H});
      return;
    }
    sending = true;
    return fetch("/api/progress", {method: "POST", body: body, credentials: "same-origin", headers: H})
      .then(function (r) {
        if (r.status === 409) return r.json().then(function (j) { blocked(j.device); });
      })
      .catch(function () {}).then(function () { sending = false; });
  }

  v.addEventListener("timeupdate", function () { if (Date.now() - lastSent > 15000) send(false); });
  v.addEventListener("pause", function () { send(false); });
  v.addEventListener("ended", function () {
    var p = send(true);
    var li = document.querySelector(".lessons li.current");
    if (li && !li.classList.contains("done")) { mark(li, true); bump(1); }
    if (d.next && auto.checked) (p || Promise.resolve()).then(function () { location.href = d.next; });
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden" && !v.paused) send(false, true);
  });

  // --- watermark: the student's email, moving every 40 s, also in fullscreen ------------
  var wm = document.getElementById("watermark");
  if (wm) {
    var move = function () {
      wm.style.left = (5 + Math.random() * 55) + "%";
      wm.style.top = (8 + Math.random() * 70) + "%";
    };
    move();
    setInterval(move, 40000);
    // The native fullscreen button would show the <video> alone (without the watermark):
    // switch to fullscreen of the whole stage instead.
    document.addEventListener("fullscreenchange", function () {
      if (document.fullscreenElement === v) {
        document.exitFullscreen().then(function () { return stage.requestFullscreen(); }).catch(function () {});
      }
    });
    v.addEventListener("dblclick", function (e) {
      e.preventDefault();
      if (document.fullscreenElement) document.exitFullscreen(); else stage.requestFullscreen().catch(function () {});
    });
  }


  // --- course content: tick a lesson by hand, like Udemy's checkboxes ------------------
  var cdone = document.getElementById("cdone"), cbar = document.getElementById("cbar"), cpct = document.getElementById("cpct");
  var total = document.querySelectorAll(".outline .lessons li").length;
  function show(n) {
    if (!cdone) return;
    cdone.textContent = n;
    var pct = total ? Math.round(100 * n / total) : 0;
    if (cbar) cbar.value = pct;
    if (cpct) cpct.textContent = pct + "%";
  }
  function mark(li, on) {   // tick + the section's "x / n" count
    if (li.classList.contains("done") === on) return;
    li.classList.toggle("done", on);
    var b = li.querySelector(".tick");
    if (b) b.setAttribute("aria-pressed", on ? "true" : "false");
    var sd = li.closest("details") && li.closest("details").querySelector(".sd");
    if (sd) sd.textContent = parseInt(sd.textContent, 10) + (on ? 1 : -1);
  }
  function bump(k) { if (cdone) show(parseInt(cdone.textContent, 10) + k); }
  Array.prototype.forEach.call(document.querySelectorAll(".outline .tick"), function (b) {
    b.addEventListener("click", function () {
      var li = b.parentNode, on = !li.classList.contains("done");
      mark(li, on);
      fetch("/api/complete", {method: "POST", credentials: "same-origin", headers: H,
                              body: JSON.stringify({course: d.course, lesson: b.dataset.lesson, completed: on})})
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function (j) { show(j.done); })
        .catch(function () { mark(li, !on); });   // not saved: undo
    });
  });
  var cur = document.querySelector(".outline li.current");
  if (cur && cur.scrollIntoView) cur.scrollIntoView({block: "center"});
  window.scrollTo(0, 0);

  // --- questions: sent with the video time when the student started writing -------------
  var ask = document.getElementById("ask");
  if (ask) {
    var qtext = document.getElementById("ask-body"), qat = document.getElementById("ask-at");
    var qerr = document.getElementById("ask-error"), qok = document.getElementById("ask-ok");
    var qbtn = document.getElementById("ask-send"), pinned = null;
    var clock = function (t) {
      t = Math.floor(t || 0);
      var h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = t % 60;
      return (h ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (s < 10 ? "0" : "") + s;
    };
    var showAt = function () { qat.textContent = clock(pinned === null ? v.currentTime : pinned); };
    v.addEventListener("timeupdate", function () { if (pinned === null) showAt(); });
    qtext.addEventListener("input", function () {
      if (pinned === null && qtext.value.trim()) { pinned = v.currentTime; showAt(); }
      if (!qtext.value.trim()) { pinned = null; showAt(); }
    });
    document.getElementById("qlist").addEventListener("click", function (e) {
      var a = e.target.closest(".qtime");
      if (!a || !v.getAttribute("src")) return;
      e.preventDefault();
      v.currentTime = parseFloat(a.dataset.t) || 0;
      window.scrollTo({top: 0, behavior: "smooth"});
    });
    ask.addEventListener("submit", function (e) {
      e.preventDefault();
      var body = qtext.value.trim();
      if (body.length < 3) return;
      qbtn.disabled = true; qerr.hidden = true; qok.hidden = true;
      var at = pinned === null ? v.currentTime : pinned;
      fetch("/api/questions", {method: "POST", credentials: "same-origin", headers: H,
                               body: JSON.stringify({course: d.course, lesson: d.lesson, position: at, body: body})})
        .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, j: j}; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.j.error || "not sent");
          var q = res.j.question, art = document.createElement("article");
          art.className = "q";
          var meta = document.createElement("p"); meta.className = "qmeta";
          var t = document.createElement("a"); t.className = "qtime"; t.href = "?t=" + Math.floor(q.position);
          t.dataset.t = q.position; t.textContent = "▶ " + q.at;
          var when = document.createElement("span"); when.className = "muted small"; when.textContent = "asked " + q.asked;
          meta.appendChild(t); meta.appendChild(when);
          var p = document.createElement("p"); p.className = "qbody"; p.textContent = q.body;
          var w = document.createElement("p"); w.className = "muted small"; w.textContent = "Waiting for an answer.";
          art.appendChild(meta); art.appendChild(p); art.appendChild(w);
          var list = document.getElementById("qlist");
          list.insertBefore(art, list.firstChild);
          qtext.value = ""; pinned = null; showAt(); qok.hidden = false;
        })
        .catch(function (err) {
          qerr.textContent = err.message === "csrf" || err.message === "login"
            ? "Your session expired: copy your text, reload the page and send it again." : err.message;
          qerr.hidden = false;
        })
        .then(function () { qbtn.disabled = false; });
    });
  }

  // --- tabs under the video (Overview / Files / Questions) ----------------------------------
  var tabs = document.querySelectorAll(".tabs .tab");
  Array.prototype.forEach.call(tabs, function (t) {
    t.addEventListener("click", function () {
      Array.prototype.forEach.call(tabs, function (o) {
        var sel = o === t;
        o.setAttribute("aria-selected", sel ? "true" : "false");
        document.getElementById(o.getAttribute("aria-controls")).hidden = !sel;
      });
    });
  });
})();
