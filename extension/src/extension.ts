import * as vscode from 'vscode';
import { BackendClient } from './backendClient';
import { Graph } from './types';

let backendClient: BackendClient | undefined;

export function activate(context: vscode.ExtensionContext) {
  backendClient = new BackendClient(context);

  const disposable = vscode.commands.registerCommand(
    'codeAnalyzer.analyzeCode',
    async () => {
      vscode.window.showInformationMessage('PySourceLens: запускаю анализ проекта…');

      const folders = vscode.workspace.workspaceFolders;
      if (!folders || folders.length === 0) {
        vscode.window.showErrorMessage(
          'PySourceLens: открой папку с Python-проектом в этом окне.'
        );
        return;
      }

      const projectPath = folders[0].uri.fsPath;
      console.log('[PySourceLens] Анализируем папку:', projectPath);

      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'PySourceLens: анализ архитектуры…',
          cancellable: false
        },
        async () => {
          try {
            const t0 = Date.now();
            const graph: Graph = await backendClient!.analyzeProject(projectPath);
            const dt = Date.now() - t0;

            console.log('[PySourceLens] Граф получен:', {
              nodes: graph.nodes.length,
              edges: graph.edges.length,
              ms: dt
            });

            vscode.window.showInformationMessage(
              `PySourceLens: анализ готов — ${graph.nodes.length} узлов, ${graph.edges.length} рёбер (за ${dt} мс).`
            );
          } catch (err: any) {
            console.error('[PySourceLens] Ошибка при анализе:', err);
            vscode.window.showErrorMessage(
              `PySourceLens: ошибка при анализе — ${err?.message || String(err)}`
            );
          }
        }
      );
    }
  );

  context.subscriptions.push(disposable);
  context.subscriptions.push({
    dispose() {
      backendClient?.dispose();
    }
  });
}

export function deactivate() {
  backendClient?.dispose();
}
