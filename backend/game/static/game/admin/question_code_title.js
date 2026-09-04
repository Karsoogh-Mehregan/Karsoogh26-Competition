(function () {
  function ready(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  ready(function () {
    var code = document.getElementById("id_code");
    var title = document.getElementById("id_title");
    if (!code || !title) {
      return;
    }

    var synced = title.value === "" || title.value === code.value;

    title.addEventListener("input", function () {
      synced = title.value === code.value;
    });

    code.addEventListener("input", function () {
      if (synced || title.value === "") {
        title.value = code.value;
        synced = true;
      }
    });
  });
})();
