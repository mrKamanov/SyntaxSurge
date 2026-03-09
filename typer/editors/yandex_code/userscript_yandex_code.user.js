// ==UserScript==
// @name         Yandex.Code / Ace — отправка позиции курсора в мост
// @description  Находит Ace Editor и при каждом движении курсора отправляет позицию на http://127.0.0.1:8765/cursor (моментально)
// @version      1.2
// @author       geoz
// @match        https://*.contest.yandex.ru/*
// @match        https://*.contest2.yandex.ru/*
// @match        https://code.yandex.ru/*
// @match        https://code.yandex-team.ru/*
// @grant        GM_xmlhttpRequest
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';

  const BRIDGE_URL = 'http://127.0.0.1:8765/cursor';
  const DEBUG = true;

  var isFrame = window !== window.top;
  console.log('[Ace→мост] Загружен. Контекст: ' + (isFrame ? 'iframe' : 'главная') + ', URL: ' + window.location.href);

  function sendPing() {
    sendPositionToBridge(0, 0, '', '', '');
  }
  function sendPositionToBridge(line, column, lineAbove, lineContent, lineBelow) {
    var payload = { line: line, column: column, lineContent: lineContent, lineAbove: lineAbove, lineBelow: lineBelow, source: 'yandex' };
    try {
      GM_xmlhttpRequest({
        method: 'POST',
        url: BRIDGE_URL,
        headers: { 'Content-Type': 'application/json' },
        data: JSON.stringify(payload),
        onload: function (r) { if (DEBUG && r.status !== 200) console.warn('[Ace→мост] Ответ не OK:', r.status); },
        onerror: function (err) { if (DEBUG) console.warn('[Ace→мост] Ошибка:', err); }
      });
    } catch (e) { if (DEBUG) console.warn('[Ace→мост] Исключение:', e); }
  }
  sendPing();

  function findAce() {
    const el = Array.from(document.querySelectorAll('*')).find(function (e) {
      return e.ace_editor || (e.env && e.env.editor) || e.session;
    });
    return el && el.env && el.env.editor ? el.env.editor : null;
  }

  function cursorToPos(cursor) {
    if (!cursor) return null;
    return { line: cursor.row + 1, column: cursor.column + 1 };
  }

  function sendPosition(editor, pos) {
    var lineAbove = '';
    var lineContent = '';
    var lineBelow = '';
    try {
      var session = editor.getSession();
      var cursor = session.selection.getCursor();
      var row = cursor.row;
      var lines = [];
      if (typeof editor.getValue === 'function') {
        lines = editor.getValue().split('\n');
      }
      if (lines.length > 0) {
        lineAbove = row > 0 && lines[row - 1] !== undefined ? (lines[row - 1] || '') : '';
        lineContent = row >= 0 && row < lines.length ? (lines[row] || '') : '';
        lineBelow = row + 1 < lines.length ? (lines[row + 1] || '') : '';
      } else if (session.getLine) {
        lineAbove = session.getLine(row - 1) || '';
        lineContent = session.getLine(row) || '';
        lineBelow = session.getLine(row + 1) || '';
      }
    } catch (e) {}
    var fullContent = '';
    try {
      if (typeof editor.getValue === 'function') fullContent = editor.getValue();
    } catch (e) {}
    var payload = {
      line: pos.line,
      column: pos.column,
      lineContent: lineContent,
      lineAbove: lineAbove,
      lineBelow: lineBelow,
      fullContent: fullContent,
      source: 'yandex'
    };
    try {
      GM_xmlhttpRequest({
        method: 'POST',
        url: BRIDGE_URL,
        headers: { 'Content-Type': 'application/json' },
        data: JSON.stringify(payload),
        onload: function (r) {
          if (DEBUG && r.status !== 200) console.warn('[Ace→мост] Ответ не OK:', r.status);
        },
        onerror: function (err) {
          if (DEBUG) console.warn('[Ace→мост] Ошибка запроса:', err);
        }
      });
    } catch (e) {
      if (DEBUG) console.warn('[Ace→мост] Исключение:', e);
    }
  }

  function attachToAce(editor) {
    var session = editor.getSession();
    if (!session || !session.selection) return;
    session.selection.on('changeCursor', function () {
      var pos = cursorToPos(session.selection.getCursor());
      if (pos) sendPosition(editor, pos);
    });
    var pos = cursorToPos(session.selection.getCursor());
    if (pos) sendPosition(editor, pos);
    if (DEBUG) console.log('[Ace→мост] Подписка на changeCursor: позиция уходит при каждом движении курсора.');
  }

  var attached = false;
  function tryAttach() {
    if (attached) return;
    var editor = findAce();
    if (editor) {
      attached = true;
      attachToAce(editor);
    }
  }

  tryAttach();
  var fallback = setInterval(function () {
    tryAttach();
    if (attached) clearInterval(fallback);
  }, 500);
  setTimeout(function () { clearInterval(fallback); }, 30000);
})();
