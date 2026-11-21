// Resume where the student stopped, save progress, go to the next lesson at the end.
(function () {
  var v = document.getElementById("player");
  if (!v) return;
  var d = v.dataset, lastSent = 0, sending = false;
  var auto = document.getElementById("autonext");
  try { if (localStorage.getItem("autonext") === "0") auto.checked = false; } catch (e) {}
  auto.addEventListener("change", function () {
    try { localStorage.setItem("autonext", auto.checked ? "1" : "0"); } catch (e) {}
  });

  v.addEventListener("loadedmetadata", function () {
    var start = parseFloat(d.start || "0");
    if (start > 5 && start < v.duration - 5) v.currentTime = start;
  });
  v.addEventListener("contextmenu", function (e) { e.preventDefault(); });

  function send(ended, beacon) {
    if (!v.duration || sending) return;
    var body = JSON.stringify({course: d.course, lesson: d.lesson, position: v.currentTime,
                               duration: v.duration, ended: !!ended});
    lastSent = Date.now();
    if (beacon) {   // page is closing: fire and forget
      fetch("/api/progress", {method: "POST", body: body, keepalive: true, credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": d.csrf}});
      return;
    }
    sending = true;
    return fetch("/api/progress", {method: "POST", body: body, credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": d.csrf}})
      .catch(function () {}).then(function () { sending = false; });
  }

  v.addEventListener("timeupdate", function () { if (Date.now() - lastSent > 15000) send(false); });
  v.addEventListener("pause", function () { send(false); });
  v.addEventListener("ended", function () {
    var p = send(true);
    var li = document.querySelector(".lessons li.current");
    if (li) li.classList.add("done");
    if (d.next && auto.checked) (p || Promise.resolve()).then(function () { location.href = d.next; });
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden" && !v.paused) send(false, true);
  });
})();
