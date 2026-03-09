import * as vscode from "vscode";
import * as http from "http";

const BRIDGE_HOST = "127.0.0.1";
const BRIDGE_PORT = 8765;
const SOURCE = "vscode";

interface BridgePayload {
  line: number;
  column: number;
  lineContent: string;
  lineAbove: string;
  lineBelow: string;
  source: string;
  languageId: string;
  fileExtension: string;
}

function getContext(editor: vscode.TextEditor): BridgePayload | null {
  const doc = editor.document;
  const pos = editor.selection.active;
  const lineIndex = pos.line;
  const colIndex = pos.character;
  const lineCount = doc.lineCount;

  const lineContent = lineIndex >= 0 && lineIndex < lineCount
    ? doc.lineAt(lineIndex).text
    : "";
  const lineAbove = lineIndex > 0
    ? doc.lineAt(lineIndex - 1).text
    : "";
  const lineBelow = lineIndex < lineCount - 1
    ? doc.lineAt(lineIndex + 1).text
    : "";

  const languageId = doc.languageId ?? "";
  const fileName = doc.fileName ?? "";
  const fileExtension = fileName.includes(".")
    ? "." + fileName.split(".").pop()!.toLowerCase()
    : "";

  return {
    line: lineIndex + 1,
    column: colIndex + 1,
    lineContent,
    lineAbove,
    lineBelow,
    source: SOURCE,
    languageId,
    fileExtension,
  };
}

function sendToBridge(payload: BridgePayload): void {
  const body = JSON.stringify(payload);
  const req = http.request(
    {
      hostname: BRIDGE_HOST,
      port: BRIDGE_PORT,
      path: "/cursor",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body, "utf8"),
      },
    },
    () => {}
  );
  req.on("error", () => {}); // мост может быть выключен
  req.write(body);
  req.end();
}

function updateBridge(editor: vscode.TextEditor | undefined): void {
  if (!editor) return;
  const payload = getContext(editor);
  if (payload) sendToBridge(payload);
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => updateBridge(editor)),
    vscode.window.onDidChangeTextEditorSelection((e) => {
      if (e.textEditor === vscode.window.activeTextEditor) {
        updateBridge(e.textEditor);
      }
    }),
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (vscode.window.activeTextEditor?.document === e.document) {
        updateBridge(vscode.window.activeTextEditor);
      }
    })
  );

  updateBridge(vscode.window.activeTextEditor);

  context.subscriptions.push(
    vscode.commands.registerCommand("syntaxsurge-bridge.checkConnection", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        void vscode.window.showInformationMessage("SyntaxSurge Bridge: откройте файл в редакторе.");
        return;
      }
      const payload = getContext(editor);
      if (!payload) return;

      try {
        const res = await new Promise<{ statusCode?: number; statusMessage?: string }>((resolve, reject) => {
          const body = JSON.stringify(payload);
          const req = http.request(
            {
              hostname: BRIDGE_HOST,
              port: BRIDGE_PORT,
              path: "/cursor",
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(body, "utf8"),
              },
            },
            (res: http.IncomingMessage) => {
              res.resume();
              resolve({ statusCode: res.statusCode, statusMessage: res.statusMessage });
            }
          );
          req.on("error", reject);
          req.write(body);
          req.end();
        });
        if (res.statusCode === 200) {
          void vscode.window.showInformationMessage(
            `SyntaxSurge Bridge: мост принял данные. Строка ${payload.line}, столбец ${payload.column}.`
          );
        } else {
          void vscode.window.showWarningMessage(
            `SyntaxSurge Bridge: ответ ${res.statusCode ?? "?"}. Запустите gui_typer.py или run.py.`
          );
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        void vscode.window.showErrorMessage(
          `SyntaxSurge Bridge: не удалось подключиться к мосту (${BRIDGE_HOST}:${BRIDGE_PORT}). ${msg}`
        );
      }
    })
  );
}

export function deactivate(): void {}
