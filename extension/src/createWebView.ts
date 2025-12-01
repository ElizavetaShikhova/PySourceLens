// extension/src/createWebView.ts
import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { Graph } from './types';

export function createWebView(
  context: vscode.ExtensionContext,
  graph: Graph,
  projectRoot: string
): vscode.WebviewPanel {
  const panel = vscode.window.createWebviewPanel(
    'pySourceLensView',
    'PySourceLens – Architecture',
    vscode.ViewColumn.Beside,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [
        vscode.Uri.file(path.join(context.extensionPath, 'media')),
      ],
    }
  );

  const mediaRoot = path.join(context.extensionPath, 'media');
  const indexPath = path.join(mediaRoot, 'index.html');

  let html = '';
  try {
    html = fs.readFileSync(indexPath, 'utf8');
  } catch (err) {
    html = `
      <!DOCTYPE html>
      <html><body>
        <h1>PySourceLens</h1>
        <pre>Не удалось прочитать index.html: ${String(err)}</pre>
      </body></html>`;
  }

  const styleUri = panel.webview.asWebviewUri(
    vscode.Uri.file(path.join(mediaRoot, 'style.css'))
  );
  const scriptUri = panel.webview.asWebviewUri(
    vscode.Uri.file(path.join(mediaRoot, 'main.js'))
  );

  html = html
    .replace('{{styleUri}}', styleUri.toString())
    .replace('{{scriptUri}}', scriptUri.toString());

  panel.webview.html = html;

  panel.webview.postMessage({
    type: 'initGraph',
    graph,
    projectRoot,
  });

  panel.webview.onDidReceiveMessage(async (msg: any) => {
    if (!msg || typeof msg !== 'object') {
      return;
    }

    switch (msg.type) {
      case 'openLocation': {
        const filePath: string = msg.file;
        const line: number = msg.line ?? 1;
        const col: number = msg.col ?? 0;

        const absPath = path.isAbsolute(filePath)
          ? filePath
          : path.join(projectRoot, filePath);

        try {
          const doc = await vscode.workspace.openTextDocument(absPath);
          const editor = await vscode.window.showTextDocument(doc, {
            preview: false,
          });

          const pos = new vscode.Position(
            Math.max(0, line - 1),
            Math.max(0, col)
          );
          editor.selection = new vscode.Selection(pos, pos);
          editor.revealRange(
            new vscode.Range(pos, pos),
            vscode.TextEditorRevealType.InCenter
          );
        } catch (err) {
          vscode.window.showErrorMessage(
            `PySourceLens: не удалось открыть файл ${absPath}: ${String(err)}`
          );
        }
        break;
      }

      case 'requestElementCode': {
        const filePath: string | undefined = msg.file;
        const startLine: number = msg.startLine ?? 1;
        const endLine: number | undefined = msg.endLine;
        const id: string = msg.id;

        if (!filePath) {
          return;
        }

        const absPath = path.isAbsolute(filePath)
          ? filePath
          : path.join(projectRoot, filePath);

        try {
          const doc = await vscode.workspace.openTextDocument(absPath);
          const startIdx = Math.max(0, startLine - 1);
          const lastLine =
            typeof endLine === 'number'
              ? Math.max(startIdx, endLine - 1)
              : Math.min(doc.lineCount - 1, startIdx + 30);

          const lines: string[] = [];
          for (let i = startIdx; i <= lastLine && i < doc.lineCount; i++) {
            lines.push(doc.lineAt(i).text);
          }

          panel.webview.postMessage({
            type: 'elementCode',
            id,
            code: lines.join('\n'),
            startLine: startIdx + 1,
          });
        } catch (err) {
          vscode.window.showErrorMessage(
            `PySourceLens: не удалось прочитать файл ${absPath}: ${String(err)}`
          );
        }
        break;
      }

      default:
        break;
    }
  });

  return panel;
}
