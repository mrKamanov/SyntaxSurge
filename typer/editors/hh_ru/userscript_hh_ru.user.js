// ==UserScript==
// @name         HH.ru — отправка позиции курсора в мост SyntaxSurge
// @description  Находит Monaco Editor на hh.ru и отправляет позицию курсора на http://127.0.0.1:8765/cursor
// @version      1.3
// @match        https://hh.ru/*
// @match        https://career.hh.ru/*
// @match        https://assessment.hh.ru/*
// @match        https://skills.hh.ru/*
// @match        https://*.hh.ru/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const BRIDGE_URL = 'http://127.0.0.1:8765/cursor';
  const DEBUG = true;
  const SOURCE = 'hh';
  const EVENT_NAME = 'hh-monaco-cursor';

  console.log('[HH.ru→мост] Загружен. URL: ' + window.location.href);

  function sendToBridge(payload) {
    try {
      GM_xmlhttpRequest({
        method: 'POST',
        url: BRIDGE_URL,
        headers: { 'Content-Type': 'application/json' },
        data: JSON.stringify(payload),
        onload: function (r) {
          if (DEBUG && r.status !== 200) console.warn('[HH.ru→мост] Ответ:', r.status);
        },
        onerror: function (err) {
          if (DEBUG) console.warn('[HH.ru→мост] Ошибка:', err);
        }
      });
    } catch (e) {
      if (DEBUG) console.warn('[HH.ru→мост] Исключение:', e);
    }
  }

  var connectedLogged = false;
  window.addEventListener(EVENT_NAME, function (e) {
    var d = e.detail || {};
    if (!connectedLogged && DEBUG) {
      connectedLogged = true;
      console.log('[HH.ru→мост] Monaco Editor подключён. Язык:', d.languageId || '');
    }
    var payload = {
      line: d.line || 0,
      column: d.column || 0,
      lineContent: d.lineContent || '',
      lineAbove: d.lineAbove || '',
      lineBelow: d.lineBelow || '',
      source: SOURCE
    };
    if (d.fullContent != null) payload.fullContent = d.fullContent;
    if (d.languageId) payload.languageId = d.languageId;
    if (d.fileExtension) payload.fileExtension = d.fileExtension;
    sendToBridge(payload);
  });

  var injectScript = function () {
    var s = document.createElement('script');
    s.textContent = '(' + function () {
      var EVENT_NAME = 'hh-monaco-cursor';
      var attached = false;
      function tryAttach() {
        if (attached) return;
        if (typeof monaco === 'undefined') return;
        var editors = monaco.editor.getEditors();
        if (!editors || editors.length === 0) return;
        var editor = editors[0];
        var model = editor.getModel();
        if (!model) return;
        attached = true;
        function send() {
          var pos = editor.getPosition();
          if (!pos) return;
          var lineNum = pos.lineNumber;
          var col = pos.column;
          var totalLines = model.getLineCount();
          var lineContent = model.getLineContent(lineNum) || '';
          var lineAbove = lineNum > 1 ? (model.getLineContent(lineNum - 1) || '') : '';
          var lineBelow = lineNum < totalLines ? (model.getLineContent(lineNum + 1) || '') : '';
          var fullContent = model.getValue();
          var langId = model.getLanguageId ? model.getLanguageId() : '';
          var ext = langId === 'sql' ? '.sql' : langId === 'python' ? '.py' : langId === 'javascript' ? '.js' : '';
          window.dispatchEvent(new CustomEvent(EVENT_NAME, {
            detail: { line: lineNum, column: col, lineAbove: lineAbove, lineContent: lineContent, lineBelow: lineBelow, fullContent: fullContent, languageId: langId, fileExtension: ext }
          }));
        }
        editor.onDidChangeCursorPosition(send);
        send();
      }
      function poll() {
        tryAttach();
        if (!attached) setTimeout(poll, 300);
      }
      poll();
    } + ')();';
    (document.head || document.documentElement).appendChild(s);
    s.remove();
  };

  function runInject() {
    if (document.body) {
      injectScript();
    } else {
      setTimeout(runInject, 100);
    }
  }

  var lastUrl = location.href;
  function checkAndInject() {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      connectedLogged = false;
      setTimeout(runInject, 500);
    }
  }

  runInject();
  setInterval(checkAndInject, 2000);
})();
