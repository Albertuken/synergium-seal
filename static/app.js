/* Sellado de anterioridad — cliente.
   Regla que gobierna este fichero: el contenido nunca se envía. Se calcula la
   huella aquí con Web Crypto y solo viaja esa cadena de 64 caracteres. */

(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  function toHex(buffer) {
    var bytes = new Uint8Array(buffer), out = '';
    for (var i = 0; i < bytes.length; i++) out += ('0' + bytes[i].toString(16)).slice(-2);
    return out;
  }

  function sha256OfBuffer(buf) {
    if (!window.crypto || !window.crypto.subtle) {
      return Promise.reject(new Error(
        'Este navegador no expone crypto.subtle. Ábrelo sobre https o en localhost.'));
    }
    return crypto.subtle.digest('SHA-256', buf).then(toHex);
  }

  function sha256OfText(text) {
    return sha256OfBuffer(new TextEncoder().encode(text));
  }

  function sha256OfFile(file) {
    return file.arrayBuffer().then(sha256OfBuffer);
  }

  /* ------------------------------------------------------------------
     Un panel = zona de arrastre + textarea + huella calculada.
     El fichero manda: si hay fichero, el texto se ignora.
     ------------------------------------------------------------------ */
  function makeHasher(opts) {
    var drop = $(opts.drop), fileInput = $(opts.file), textArea = $(opts.text);
    var digestBox = $(opts.digestBox), digestValue = $(opts.digestValue);
    var button = $(opts.button);
    var state = { digest: null, source: null, busy: false };

    function setDigest(hex, source) {
      state.digest = hex;
      state.source = source;
      digestValue.textContent = hex || '';
      digestBox.hidden = !hex;
      button.disabled = !hex || state.busy;
      if (opts.onChange) opts.onChange();
    }

    function fromFile(file) {
      if (!file) return;
      drop.classList.add('has-file');
      drop.querySelector('strong').textContent = file.name;
      drop.querySelector('span').textContent =
        (file.size / 1024 < 1024)
          ? Math.max(1, Math.round(file.size / 1024)) + ' KB'
          : (file.size / 1048576).toFixed(1) + ' MB';
      sha256OfFile(file).then(function (hex) { setDigest(hex, 'file'); })
        .catch(function (err) {
          drop.classList.remove('has-file');
          alert('No se pudo leer el fichero: ' + err.message);
        });
    }

    drop.addEventListener('click', function () { fileInput.click(); });
    drop.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
    });
    fileInput.addEventListener('change', function () { fromFile(fileInput.files[0]); });

    ['dragenter', 'dragover'].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('over'); });
    });
    drop.addEventListener('drop', function (e) {
      if (e.dataTransfer.files && e.dataTransfer.files[0]) fromFile(e.dataTransfer.files[0]);
    });

    textArea.addEventListener('input', function () {
      if (state.source === 'file') return;   // un fichero cargado gana al texto
      var value = textArea.value;
      if (!value) { setDigest(null, null); return; }
      sha256OfText(value).then(function (hex) { setDigest(hex, 'text'); });
    });

    return {
      get digest() { return state.digest; },
      setBusy: function (v) { state.busy = v; button.disabled = v || !state.digest; }
    };
  }

  /* ---------------------------- pestañas ---------------------------- */
  document.querySelectorAll('.tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      document.querySelectorAll('.tab').forEach(function (t) {
        if (t === tab) t.setAttribute('aria-current', 'page');
        else t.removeAttribute('aria-current');
      });
      ['sellar', 'verificar'].forEach(function (v) {
        $('view-' + v).hidden = (v !== tab.getAttribute('data-view'));
      });
    });
  });

  /* ---------------------------- sellar ------------------------------ */
  var sealer = makeHasher({
    drop: 'drop-seal', file: 'file-seal', text: 'text-seal',
    digestBox: 'digest-seal', digestValue: 'digest-seal-value', button: 'btn-seal'
  });

  $('btn-seal').addEventListener('click', function () {
    var box = $('seal-result');
    sealer.setBusy(true);
    box.innerHTML = '<div class="result pending"><h3><span class="spinner"></span>Sellando…</h3>' +
                    '<p>Enviando la huella a los calendarios de OpenTimestamps.</p></div>';

    fetch('/api/seal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hash: sealer.digest, label: $('label-seal').value })
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        sealer.setBusy(false);
        if (!res.ok) {
          box.innerHTML = '<div class="result bad"><h3>No se pudo sellar</h3><p></p></div>';
          box.querySelector('p').textContent = res.body.error || 'Error desconocido.';
          return;
        }
        var s = res.body;
        box.innerHTML =
          '<div class="result pending">' +
            '<h3>Sellado</h3>' +
            '<p>Queda <strong>pendiente</strong> hasta que entre en un bloque de Bitcoin, ' +
            'normalmente unas horas. Ya es válido desde ahora: la fecha registrada es esta.</p>' +
            '<dl>' +
              '<dt>registro</dt><dd class="js-id"></dd>' +
              '<dt>sellado</dt><dd class="js-created"></dd>' +
              '<dt>huella</dt><dd class="js-digest"></dd>' +
            '</dl>' +
            '<div class="actions">' +
              '<a class="btn btn-ghost js-proof" href="#" download>Descargar prueba .ots</a>' +
            '</div>' +
          '</div>';
        box.querySelector('.js-id').textContent = s.id;
        box.querySelector('.js-created').textContent = s.created_at;
        box.querySelector('.js-digest').textContent = s.digest;
        box.querySelector('.js-proof').href = '/api/stamp/' + encodeURIComponent(s.id) + '/proof';
      })
      .catch(function (err) {
        sealer.setBusy(false);
        box.innerHTML = '<div class="result bad"><h3>No se pudo sellar</h3><p></p></div>';
        box.querySelector('p').textContent = err.message;
      });
  });

  /* --------------------------- verificar ---------------------------- */
  var verifier = makeHasher({
    drop: 'drop-verify', file: 'file-verify', text: 'text-verify',
    digestBox: 'digest-verify', digestValue: 'digest-verify-value', button: 'btn-verify'
  });

  $('btn-verify').addEventListener('click', function () {
    var box = $('verify-result');
    verifier.setBusy(true);
    box.innerHTML = '<div class="result pending"><h3><span class="spinner"></span>Comprobando…</h3></div>';

    fetch('/api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hash: verifier.digest })
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        verifier.setBusy(false);
        if (!res.found) {
          box.innerHTML =
            '<div class="result bad"><h3>Sin sello registrado</h3>' +
            '<p>Esta huella no consta aquí. Si esperabas encontrarla, el contenido ' +
            'ha cambiado: basta un carácter para que la huella sea otra.</p></div>';
          return;
        }
        var items = res.stamps.map(function (s) {
          return '<dl>' +
            '<dt>registro</dt><dd>' + s.id + '</dd>' +
            '<dt>sellado</dt><dd>' + s.created_at + '</dd>' +
            '<dt>estado</dt><dd>' + (s.status === 'anchored'
              ? 'anclado en Bitcoin' + (s.bitcoin_heights.length ? ' · bloque ' + s.bitcoin_heights.join(', ') : '')
              : 'pendiente de anclaje') + '</dd>' +
            (s.label ? '<dt>etiqueta</dt><dd class="js-label"></dd>' : '') +
          '</dl>';
        }).join('');
        box.innerHTML =
          '<div class="result ok"><h3>Sello encontrado</h3>' +
          '<p>Este contenido exacto estaba registrado en la fecha indicada.</p>' +
          items + '</div>';
        // las etiquetas son texto de usuario: se insertan como texto, nunca como HTML
        var labelled = res.stamps.filter(function (s) { return s.label; });
        box.querySelectorAll('.js-label').forEach(function (node, i) {
          node.textContent = labelled[i].label;
        });
      })
      .catch(function (err) {
        verifier.setBusy(false);
        box.innerHTML = '<div class="result bad"><h3>Error al comprobar</h3><p></p></div>';
        box.querySelector('p').textContent = err.message;
      });
  });
})();
