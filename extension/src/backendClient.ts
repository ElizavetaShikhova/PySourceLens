import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';
import { Graph } from './types';

type BackendCommand = 'version' | 'analyze';

interface BackendRequest {
  cmd: BackendCommand;
  path?: string;
  pretty?: boolean;
}

interface AnalyzeResponse {
  ok: boolean;
  graph?: Graph;
  error?: string;
  [key: string]: any;
}

export class BackendClient implements vscode.Disposable {
  private process: cp.ChildProcessWithoutNullStreams | null = null;
  private buffer = '';
  private pending: Array<{
    resolve: (value: any) => void;
    reject: (reason?: any) => void;
  }> = [];

  private pythonPath: string;

  constructor(private context: vscode.ExtensionContext) {
    /*this.pythonPath =
      vscode.workspace
        .getConfiguration('codeAnalyzer')
        .get<string>('pythonPath') || 'python';*/
    this.pythonPath = "python";
  }

  
  private getCliScriptPath(): string {
    // backend/cli.py лежит рядом с package.json
    return this.context.asAbsolutePath(path.join('backend', 'cli.py'));
  }

  
  private ensureProcessStarted() {
    if (this.process) {
      return;
    }

    const scriptPath = this.getCliScriptPath();
    console.log('[PySourceLens] pythonPath =', this.pythonPath);
    console.log('[PySourceLens] cli script path =', scriptPath);

    try {
      this.process = cp.spawn(
        this.pythonPath,
        [scriptPath, 'serve'],
        {
          cwd: path.dirname(scriptPath),
          stdio: ['pipe', 'pipe', 'pipe']
        }
      );
    } catch (err) {
      console.error('[PySourceLens] spawn error (sync):', err);
      vscode.window.showErrorMessage(
        `PySourceLens: не удалось запустить Python: ${String(err)}`
      );
      throw err;
    }

    this.process.on('error', (err) => {
      console.error('[PySourceLens] backend process error:', err);
      vscode.window.showErrorMessage(
        `PySourceLens: ошибка запуска backend-процесса: ${String(err)}`
      );
      // заваливаем все ожидающие запросы
      this.pending.forEach(p => p.reject(err));
      this.pending = [];
      this.process = null;
    });

    this.process.stdout.on('data', (data: Buffer) => {
      this.handleStdoutData(data.toString('utf8'));
    });

    this.process.stderr.on('data', (data: Buffer) => {
      const msg = data.toString('utf8');
      console.error('[Code Analyzer backend stderr]', msg);
      vscode.window.showWarningMessage(`Code Analyzer backend: ${msg}`);
    });

    this.process.on('exit', (code, signal) => {
      console.log(`Backend process exited with code=${code}, signal=${signal}`);
      const err = new Error('Backend process exited');
      this.pending.forEach(p => p.reject(err));
      this.pending = [];
      this.process = null;
    });
  }


  
  private handleStdoutData(chunk: string) {
    this.buffer += chunk;

    let newlineIndex: number;
    while ((newlineIndex = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, newlineIndex).trim();
      this.buffer = this.buffer.slice(newlineIndex + 1);

      if (!line) {
        continue;
      }

      let json: any;
      try {
        json = JSON.parse(line);
      } catch (e) {
        console.error('Invalid JSON from backend:', line);
        continue;
      }

      const pending = this.pending.shift();
      if (!pending) {
        console.warn('Received backend response with no pending request', json);
        continue;
      }

      if (json && json.ok === false) {
        pending.reject(new Error(json.error || 'Backend error'));
      } else {
        pending.resolve(json);
      }
    }
  }

  sendRequest<T = any>(request: BackendRequest): Promise<T> {
    this.ensureProcessStarted();

    if (!this.process || !this.process.stdin) {
      return Promise.reject(new Error('Backend process is not running'));
    }

    return new Promise<T>((resolve, reject) => {
      this.pending.push({ resolve, reject });
      const line = JSON.stringify(request) + '\n';
      this.process!.stdin.write(line, 'utf8');
    });
  }


  async analyzeProject(projectPath: string): Promise<Graph> {
    const response = await this.sendRequest<AnalyzeResponse>({
      cmd: 'analyze',
      path: projectPath,
      pretty: false
    });

    if (!response.ok || !response.graph) {
      throw new Error(response.error || 'Unknown error from backend');
    }

    return response.graph;
  }

  dispose() {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
  }
}
