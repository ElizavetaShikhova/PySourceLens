import * as vscode from 'vscode';
import { BackendClient } from './backendClient';
import { createWebView } from './createWebView';
import { Graph } from './types';

export function activate(context: vscode.ExtensionContext) {
  const disposable = vscode.commands.registerCommand(
    'codeAnalyzer.analyzeCode',
    async () => {
      const folders = vscode.workspace.workspaceFolders;
      if (!folders || folders.length === 0) {
        vscode.window.showErrorMessage(
          'PySourceLens: нет открытой папки проекта'
        );
        return;
      }

      const projectRoot = folders[0].uri.fsPath;
      const client = new BackendClient(context);

      try {
        const started = Date.now();

        const graph: Graph = await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Window,
            title: 'PySourceLens: анализ архитектуры…',
          },
          () => client.analyzeProject(projectRoot)
        );

        const elapsed = Date.now() - started;
        vscode.window.setStatusBarMessage(
          `PySourceLens: анализ готов — ${graph.nodes.length} узлов, ${graph.edges.length} рёбер (за ${elapsed} мс)`,
          5000
        );

        createWebView(context, graph, projectRoot);
      } catch (err: any) {
        vscode.window.showErrorMessage(
          `PySourceLens: ошибка анализа — ${err?.message || String(err)}`
        );
        console.error('[PySourceLens] analyze error:', err);
      } finally {
        client.dispose();
      }
    }
  );

  context.subscriptions.push(disposable);
}

export function deactivate() {}
