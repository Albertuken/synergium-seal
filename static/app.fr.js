/* Sellado de anterioridad — cliente.

   Regla que gobierna este fichero: el contenido nunca se envía. La huella se
   calcula aquí con Web Crypto y al servidor solo viaja esa cadena de 64
   caracteres. Todo lo demás es lectura de instrumento. */

(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var subtle = window.crypto && window.crypto.subtle;

  function hex(buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (b) {
      return ('0' + b.toString(16)).slice(-2);
    }).join('');
  }
  function sha256(buf) { return subtle.digest('SHA-256', buf).then(hex); }

  function esc(s) { return String(s == null ? '' : s); }

  /* La misma escala que la del panel de entrada, pero de una huella ya fija.
     Se usa en el resultado: el momento en que el sello existe merece verse,
     no solo leerse en una fila de texto. */
  function scaleOf(hex) {
    var wrap = document.createElement('div');
    wrap.className = 'scale';
    wrap.setAttribute('role', 'img');
    wrap.setAttribute('aria-label', 'Empreinte SHA-256 du document scellé');
    for (var i = 0; i < 64; i++) {
      var b = document.createElement('i');
      var v = parseInt(hex[i], 16);
      b.style.height = (4 + (isNaN(v) ? 0 : v / 15) * 96) + '%';
      wrap.appendChild(b);
    }
    return wrap;
  }

  /* ── Un panel de medida: entrada (fichero o texto) → huella → escala ──
     La escala son 64 barras, una por dígito hexadecimal. Cambia un byte del
     fichero y salta entera: eso es lo que hace útil a un hash, mostrado. */
  function panel(o) {
    var drop = $(o.drop), file = $(o.file), text = $(o.text);
    var out = $(o.hash), len = $(o.len), btn = $(o.btn);
    var scale = $(o.scale);
    var bars = [];
    for (var i = 0; i < 64; i++) {
      var b = document.createElement('i');
      scale.appendChild(b);
      bars.push(b);
    }

    var VACIO = '—'.repeat(24);
    var state = { digest: null, fromFile: false, busy: false };

    function paint(h) {
      out.innerHTML = '';
      var head = document.createElement('b');       // los 8 primeros: lo que se compara de un vistazo
      head.textContent = h.slice(0, 8);
      out.appendChild(head);
      out.appendChild(document.createTextNode(h.slice(8)));
      for (var i = 0; i < 64; i++) {
        bars[i].style.height = (4 + (parseInt(h[i], 16) / 15) * 96) + '%';
      }
    }
    function clear() {
      out.textContent = VACIO;
      for (var i = 0; i < 64; i++) bars[i].style.height = '4%';
    }
    function set(h, label) {
      state.digest = h;
      len.textContent = label;
      if (h) paint(h); else clear();
      btn.disabled = !h || state.busy;
    }

    function fromFile(f) {
      if (!f) return;
      state.fromFile = true;
      drop.classList.add('has');
      $(o.dropName).textContent = f.name;
      $(o.dropMeta).textContent = f.size < 1048576
        ? Math.max(1, Math.round(f.size / 1024)) + ' KB'
        : (f.size / 1048576).toFixed(1) + ' MB';
      f.arrayBuffer().then(sha256).then(function (h) {
        set(h, Math.round(f.size / 1024) + ' KB');
      }).catch(function (e) {
        drop.classList.remove('has');
        set(null, 'le fichier n’a pas pu être lu');
      });
    }

    drop.addEventListener('click', function () { file.click(); });
    drop.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); file.click(); }
    });
    file.addEventListener('change', function () { fromFile(file.files[0]); });
    ['dragenter', 'dragover'].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('over'); });
    });
    drop.addEventListener('drop', function (e) {
      if (e.dataTransfer.files && e.dataTransfer.files[0]) fromFile(e.dataTransfer.files[0]);
    });

    text.addEventListener('input', function () {
      if (state.fromFile) return;               // un fichero cargado gana al texto
      var v = text.value;
      if (!v) { set(null, 'aucune entrée'); return; }
      sha256(new TextEncoder().encode(v)).then(function (h) {
        set(h, v.length + ' caractères');
      });
    });

    clear();
    return {
      get digest() { return state.digest; },
      busy: function (v) { state.busy = v; btn.disabled = v || !state.digest; }
    };
  }

  /* ── Sin contexto seguro no hay crypto.subtle: se dice, no se finge ── */
  if (!subtle) {
    document.querySelectorAll('textarea, .drop, .btn').forEach(function (el) {
      el.setAttribute('disabled', 'disabled');
      el.style.opacity = '.4';
    });
    document.querySelectorAll('.privacy span:last-child').forEach(function (el) {
      el.textContent = 'Ce navigateur ne peut pas calculer l’empreinte ici : une connexion sécurisée (https) est nécessaire.';
    });
    return;
  }

  /* ── Pestañas ────────────────────────────────────────────────────── */
  document.querySelectorAll('.tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      document.querySelectorAll('.tab').forEach(function (t) {
        if (t === tab) t.setAttribute('aria-current', 'page');
        else t.removeAttribute('aria-current');
      });
      ['sellar', 'verificar'].forEach(function (v) {
        $('view-' + v).hidden = (v !== tab.getAttribute('data-view'));
      });
      window.scrollTo({ top: 0, behavior: 'auto' });
    });
  });

  /* ── Sellar ──────────────────────────────────────────────────────── */
  var S = panel({
    drop: 'drop-s', dropName: 'drop-s-n', dropMeta: 'drop-s-m', file: 'file-s',
    text: 'text-s', hash: 'hash-s', len: 'len-s', btn: 'btn-s', scale: 'scale-s'
  });

  $('btn-s').addEventListener('click', function () {
    var box = $('res-s');
    S.busy(true);
    box.innerHTML = '<div class="result"><span class="tag sig"><span class="spin"></span>Envoi aux calendriers</span>'
                  + '<h2>Scellement…</h2></div>';

    fetch('/api/seal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hash: S.digest, label: $('label-s').value })
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
      .then(function (res) {
        S.busy(false);
        if (!res.ok) {
          box.innerHTML = '<div class="result bad"><span class="tag sig">Erreur</span>'
                        + '<h2>Impossible de sceller</h2><p></p></div>';
          box.querySelector('p').textContent = res.b.error || 'Erreur inconnue.';
          return;
        }
        var s = res.b;
        box.innerHTML =
          '<div class="result ok">'
          + '<span class="tag ok">Enregistré</span>'
          + '<h2>Scellé</h2>'
          + '<p>Il reste <b>en attente</b> jusqu’à son entrée dans un bloc Bitcoin, en général quelques heures. '
          + 'Il est déjà valable dès maintenant : la date enregistrée est celle-ci.</p>'
          + '<div class="j-scale"></div>'
          + '<div class="scale-legend"><span class="tag">chiffre 1</span>'
          +   '<span class="tag">voici l’empreinte qui a été enregistrée</span>'
          +   '<span class="tag">64</span></div>'
          + '<dl>'
          +   '<div><dt>Enregistrement</dt><dd class="j-id"></dd></div>'
          +   '<div><dt>Scellé le</dt><dd class="j-at"></dd></div>'
          +   '<div><dt>Empreinte</dt><dd class="j-h"></dd></div>'
          + '</dl>'
          + '<div class="actions"><a class="btn btn-2 j-p" href="#" download>Télécharger la preuve .ots</a></div>'
          + '</div>';
        box.querySelector('.j-scale').replaceWith(scaleOf(s.digest));
        box.querySelector('.j-id').textContent = esc(s.id);
        box.querySelector('.j-at').textContent = esc(s.created_at);
        box.querySelector('.j-h').textContent = esc(s.digest);
        box.querySelector('.j-p').href = '/api/stamp/' + encodeURIComponent(s.id) + '/proof';
      })
      .catch(function (e) {
        S.busy(false);
        box.innerHTML = '<div class="result bad"><h2>Impossible de sceller</h2><p></p></div>';
        box.querySelector('p').textContent = e.message;
      });
  });

  /* ── Verificar ───────────────────────────────────────────────────── */
  var V = panel({
    drop: 'drop-v', dropName: 'drop-v-n', dropMeta: 'drop-v-m', file: 'file-v',
    text: 'text-v', hash: 'hash-v', len: 'len-v', btn: 'btn-v', scale: 'scale-v'
  });

  $('btn-v').addEventListener('click', function () {
    var box = $('res-v');
    V.busy(true);
    box.innerHTML = '<div class="result"><span class="tag sig"><span class="spin"></span>Consultation</span>'
                  + '<h2>Vérification…</h2></div>';

    fetch('/api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hash: V.digest })
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        V.busy(false);
        if (!res.found) {
          box.innerHTML =
            '<div class="result bad"><span class="tag sig">Aucune correspondance</span>'
            + '<h2>Aucun sceau enregistré</h2>'
            + '<p>Cette empreinte n’est pas au registre. Si vous vous attendiez à la trouver, le contenu a '
            + 'changé : un seul caractère suffit pour que l’empreinte soit autre.</p></div>';
          return;
        }
        var filas = res.stamps.map(function (s) {
          var estado = s.status === 'anchored'
            ? 'ancré dans Bitcoin' + (s.bitcoin_heights.length ? ' · bloc ' + s.bitcoin_heights.join(', ') : '')
            : 'en attente d’ancrage';
          return '<dl>'
            + '<div><dt>Enregistrement</dt><dd>' + esc(s.id) + '</dd></div>'
            + '<div><dt>Scellé le</dt><dd>' + esc(s.created_at) + '</dd></div>'
            + '<div><dt>État</dt><dd>' + estado + '</dd></div>'
            + (s.label ? '<div><dt>Étiquette</dt><dd class="j-l"></dd></div>' : '')
            + '</dl>';
        }).join('');
        box.innerHTML =
          '<div class="result ok"><span class="tag ok">Correspondance</span>'
          + '<h2>Sceau trouvé</h2>'
          + '<p>Ce contenu exact était enregistré à la date indiquée.</p>'
          + filas + '</div>';
        // las etiquetas son texto de usuario: se insertan como texto, nunca como HTML
        var conEtiqueta = res.stamps.filter(function (s) { return s.label; });
        box.querySelectorAll('.j-l').forEach(function (n, i) { n.textContent = conEtiqueta[i].label; });
      })
      .catch(function (e) {
        V.busy(false);
        box.innerHTML = '<div class="result bad"><h2>Erreur lors de la vérification</h2><p></p></div>';
        box.querySelector('p').textContent = e.message;
      });
  });
})();
