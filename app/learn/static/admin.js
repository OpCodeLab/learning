// "Copy link" buttons on the invite pages.
(function () {
  var b = document.getElementById("copy");
  if (!b) return;
  b.addEventListener("click", function (e) {
    e.preventDefault();
    var input = document.getElementById(b.dataset.target);
    input.select();
    var done = function () { b.textContent = "Copied"; };
    if (navigator.clipboard) navigator.clipboard.writeText(input.value).then(done, function () { document.execCommand("copy"); done(); });
    else { document.execCommand("copy"); done(); }
  });
})();
