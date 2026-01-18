const vscode = acquireVsCodeApi();

let currentGraph = null;
let projectRoot = '';
let nodeById = {};
let moduleNodes = [];
let currentView = 'project'; // 'project' | 'module' | 'element'
let currentModulePath = null;
let currentElementId = null;

const fileTreeEl = document.getElementById('file-tree');
const levelKindEl = document.getElementById('level-kind');
const levelTitleEl = document.getElementById('level-title');
const diagramEl = document.getElementById('diagram');
const detailsEl = document.getElementById('details');
const codeBlockEl = document.getElementById('code-block');
const sidebarModuleInfoEl = document.getElementById('sidebar-module-info');
const sidebarElementInfoEl = document.getElementById('sidebar-element-info');
const detailsHeaderEl = document.getElementById('details-header');

window.addEventListener('message', event => {
  const msg = event.data;
  if (!msg || typeof msg !== 'object') return;

  if (msg.type === 'initGraph') {
    currentGraph = msg.graph;
    projectRoot = msg.projectRoot;
    console.log('Получен граф:', currentGraph);
    nodeById = {};
    (currentGraph.nodes || []).forEach(n => { nodeById[n.id] = n; });
    moduleNodes = (currentGraph.nodes || []).filter(isModuleNode);
    renderFileTree();
    showProjectView();
  } else if (msg.type === 'elementCode') {
    if (msg.id === currentElementId) {
      renderElementCode(msg.code, msg.startLine);
    }
  }
});


function isModuleNode(node) {
  const d = node.data || {};
  return !!d.path && String(d.path).endsWith('.py') && !d.type;
}

function getModuleNodeByPath(path) {
  return moduleNodes.find(m => (m.data && m.data.path) === path);
}

function getModuleForElementId(id) {
  let best = null;
  for (const m of moduleNodes) {
    const prefix = m.id;
    if (id === prefix || id.startsWith(prefix + '.')) {
      if (!best || prefix.length > best.id.length) {
        best = m;
      }
    }
  }
  return best;
}

function getOutgoingCalls(id) {
  if (!currentGraph) return [];
  const out = [];
  for (const e of currentGraph.edges || []) {
    if (e.from === id) out.push(e.to);
  }
  return out;
}

function niceFileName(pathStr) {
  if (!pathStr) return '';
  const norm = pathStr.replace(/\\/g, '/');
  const parts = norm.split('/');
  return parts[parts.length - 1];
}


function renderFileTree() {
  fileTreeEl.innerHTML = '';
  if (!currentGraph) return;

  const paths = new Set();
  for (const n of moduleNodes) {
    const p = n.data && n.data.path;
    if (p) paths.add(String(p));
  }
  const sorted = Array.from(paths).sort();

  sorted.forEach(p => {
    const div = document.createElement('div');
    const normalizedPath = p.replace(/\\/g, '/');
    let displayPath = normalizedPath;

    if (projectRoot && displayPath.startsWith(projectRoot)) {
      displayPath = displayPath.substring(projectRoot.length);
      if (displayPath.startsWith('/')) {
        displayPath = displayPath.substring(1);
      }
    }

    const depth = displayPath.split('/').length - 1;

    const fileName = displayPath.split('/').pop() || normalizedPath.split('/').pop();

    div.className = 'tree-item tree-indent-' + Math.min(depth, 4);
    div.textContent = fileName;
    div.title = displayPath; 
    div.dataset.path = p;

    div.onclick = () => {
      selectTreeItem(p);
      showModuleView(p);
    };

    fileTreeEl.appendChild(div);
  });
}

function selectTreeItem(pathStr) {
  currentModulePath = pathStr;
  const items = fileTreeEl.querySelectorAll('.tree-item');
  items.forEach(i => {
    if (i.dataset.path === pathStr) i.classList.add('selected');
    else i.classList.remove('selected');
  });
}


function showProjectView() {
  currentView = 'project';
  currentModulePath = null;
  currentElementId = null;
  levelKindEl.textContent = 'УРОВЕНЬ: ПРОЕКТ';
  levelTitleEl.textContent = '';
  sidebarModuleInfoEl.innerHTML = '';
  sidebarElementInfoEl.innerHTML = '';
  codeBlockEl.textContent = '';
  detailsHeaderEl.innerHTML = '';

  diagramEl.innerHTML = '';
  const title = document.createElement('h3');
  title.textContent = 'Модули и входные точки';
  diagramEl.appendChild(title);

  const modulesWrap = document.createElement('div');
  (moduleNodes || []).forEach(m => {
    const d = m.data || {};
    const btn = document.createElement('div');
    btn.className = 'module-node';
    btn.title = d.path || m.id;
    btn.onclick = () => {
      selectTreeItem(d.path);
      showModuleView(d.path);
    };

    const isEntry = isEntryModule(m);
    if (isEntry) btn.classList.add('entry');

    const icon = document.createElement('span');
    icon.className = 'rocket';
    icon.textContent = isEntry ? '🚀' : '📄';

    const label = document.createElement('span');
    label.textContent = niceFileName(d.path) || m.id;

    btn.appendChild(icon);
    btn.appendChild(label);
    modulesWrap.appendChild(btn);
  });
  diagramEl.appendChild(modulesWrap);

  const edgesTitle = document.createElement('div');
  edgesTitle.className = 'muted';
  edgesTitle.style.marginTop = '8px';
  edgesTitle.textContent = 'Зависимости между модулями:';
  diagramEl.appendChild(edgesTitle);

  const edgesDiv = document.createElement('div');
  edgesDiv.className = 'edge-list';

  const moduleDeps = buildModuleDependencies();
  if (moduleDeps.length === 0) {
    const no = document.createElement('div');
    no.className = 'muted';
    no.textContent = 'Нет обнаруженных межмодульных вызовов.';
    edgesDiv.appendChild(no);
  } else {
    moduleDeps.forEach(dep => {
      const div = document.createElement('div');
      div.className = 'edge-item';
      div.textContent = `${dep.fromLabel} → ${dep.toLabel}`;
      edgesDiv.appendChild(div);
    });
  }

  diagramEl.appendChild(edgesDiv);

  detailsHeaderEl.innerHTML = '<span class="muted">Подсказка:</span> нажмите на модуль или файл слева, чтобы перейти на уровень "Модуль".';
  codeBlockEl.textContent = '';
  updateNavigationButtons();
}

function isEntryModule(moduleNode) {
  if (!currentGraph) return false;
  const d = moduleNode.data || {};
  const pathStr = d.path;
  if (!pathStr) return false;
  for (const n of currentGraph.nodes || []) {
    const nd = n.data || {};
    if (nd.type === 'entry_point_stub' && nd.file === pathStr) {
      return true;
    }
  }
  return false;
}

function buildModuleDependencies() {
  if (!currentGraph) return [];
  const result = [];
  const moduleById = {};
  moduleNodes.forEach(m => { moduleById[m.id] = m; });

  function moduleOfNodeId(id) {
    if (moduleById[id]) return moduleById[id];
    let best = null;
    for (const m of moduleNodes) {
      const prefix = m.id;
      if (id === prefix || id.startsWith(prefix + '.')) {
        if (!best || prefix.length > best.id.length) {
          best = m;
        }
      }
    }
    return best;
  }

  const seen = new Set();
  for (const e of currentGraph.edges || []) {
    const fromM = moduleOfNodeId(e.from);
    const toM = moduleOfNodeId(e.to);
    if (!fromM || !toM) continue;
    if (fromM.id === toM.id) continue;
    const key = fromM.id + '→' + toM.id;
    if (seen.has(key)) continue;
    seen.add(key);

    const fromPath = (fromM.data && fromM.data.path) || fromM.id;
    const toPath = (toM.data && toM.data.path) || toM.id;
    result.push({
      fromId: fromM.id,
      toId: toM.id,
      fromLabel: niceFileName(fromPath),
      toLabel: niceFileName(toPath),
    });
  }
  return result;
}

function showModuleView(modulePath) {
  currentView = 'module';
  currentModulePath = modulePath;
  currentElementId = null;
  codeBlockEl.textContent = '';
  detailsHeaderEl.textContent = '';

  const outgoingCalls = {};
  for (const edge of currentGraph.edges || []) {
    if (!outgoingCalls[edge.from]) {
      outgoingCalls[edge.from] = [];
    }
    outgoingCalls[edge.from].push(edge.to);
  }
  
  const moduleNode = getModuleNodeByPath(modulePath);
  if (!moduleNode) {
    levelKindEl.textContent = 'УРОВЕНЬ: МОДУЛЬ';
    levelTitleEl.textContent = modulePath;
    diagramEl.innerHTML = '<div class="muted">Модуль не найден в графе.</div>';
    sidebarModuleInfoEl.innerHTML = '';
    sidebarElementInfoEl.innerHTML = '';
    return;
  }

  const moduleName = moduleNode.id;
  levelKindEl.textContent = 'УРОВЕНЬ: МОДУЛЬ';
  levelTitleEl.textContent = `[${modulePath}]`;

  const classes = [];
  const functions = [];

  for (const n of currentGraph.nodes || []) {
    const d = n.data || {};
    if (Array.isArray(d.methods) && (n.id === moduleName || n.id.startsWith(moduleName + '.'))) {
      classes.push(n);
    } else if (Array.isArray(d.args) && !Array.isArray(d.methods) &&
               (n.id === moduleName || n.id.startsWith(moduleName + '.'))) {
      functions.push(n);
    }
  }

  const clsLines = classes.map(c => `<li>${escapeHtml(c.id)}</li>`).join('');
  const fnLines = functions.map(f => `<li><span class="linkish" data-element-id="${escapeAttr(f.id)}">${escapeHtml(f.id)}</span></li>`).join('');

  sidebarModuleInfoEl.innerHTML = `
    <h4>Классы</h4>
    <ul>${clsLines || '<li class="muted">нет</li>'}</ul>
    <h4>Функции</h4>
    <ul>${fnLines || '<li class="muted">нет</li>'}</ul>
  `;
  sidebarElementInfoEl.innerHTML = '';

  sidebarModuleInfoEl.querySelectorAll('[data-element-id]').forEach(el => {
    el.addEventListener('click', () => {
      const id = el.getAttribute('data-element-id');
      if (id) showElementView(id);
    });
  });

  diagramEl.innerHTML = '';
  const h3 = document.createElement('h3');
  h3.textContent = `Структура модуля ${moduleName}`;
  diagramEl.appendChild(h3);

  if (classes.length === 0 && functions.length === 0) {
    const div = document.createElement('div');
    div.className = 'muted';
    div.textContent = 'Классы и функции не найдены.';
    diagramEl.appendChild(div);
    return;
  }

  classes.forEach(clsNode => {
    const d = clsNode.data || {};
    const box = document.createElement('div');
    box.style.marginBottom = '8px';

    const title = document.createElement('div');
    title.innerHTML = `● <span class="linkish" data-element-id="${escapeAttr(clsNode.id)}">${escapeHtml(clsNode.id)}</span>`;
    box.appendChild(title);

    const methods = Array.isArray(d.methods) ? d.methods : [];
    methods.forEach(m => {
      const methodId = clsNode.id + '.' + m.name;
      const calls = outgoingCalls[methodId] || [];

      const methodLine = document.createElement('div');
      methodLine.style.cursor = 'pointer';
      methodLine.textContent = m.name + '():';
      methodLine.title = 'Показать детали метода';
      methodLine.onclick = () => showElementView(methodId);
      box.appendChild(methodLine);

      if (calls.length > 0) {
        calls.forEach(id => {
          const callLine = document.createElement('div');
          callLine.className = 'linkish';
          callLine.style.marginLeft = '18px';
          callLine.textContent = '→ ' + id;
          callLine.title = 'Перейти к элементу';
          callLine.onclick = () => showElementView(id);
          diagramEl.appendChild(callLine);
          box.appendChild(callLine);
        });
      } else {
        const noCall = document.createElement('div');
        noCall.style.color = 'var(--fg-muted)';
        noCall.style.fontStyle = 'italic';
        noCall.textContent = '— нет вызовов';
        box.appendChild(noCall);
      }
    });
           
    diagramEl.appendChild(box);
  });

  if (functions.length) {
    const sep = document.createElement('div');
    sep.style.marginTop = '8px';
    sep.innerHTML = '<span class="muted">Глобальные функции:</span>';
    diagramEl.appendChild(sep);

    functions.forEach(fnNode => {
      const calls = outgoingCalls[fnNode.id] || [];

      const funcLine = document.createElement('div');
      funcLine.style.cursor = 'pointer';
      funcLine.textContent = fnNode.id + ':';
      funcLine.title = 'Показать детали функции';
      funcLine.onclick = () => showElementView(fnNode.id);
      diagramEl.appendChild(funcLine);

      if (calls.length > 0) {
        calls.forEach(id => {
          const callLine = document.createElement('div');
          callLine.className = 'linkish';
          callLine.textContent = '→ ' + id;
          callLine.title = 'Перейти к элементу';
          callLine.onclick = () => showElementView(id);
          diagramEl.appendChild(callLine);
        });
      } else {
        const noCall = document.createElement('div');
        noCall.style.marginLeft = '18px';
        noCall.style.color = 'var(--fg-muted)';
        noCall.style.fontStyle = 'italic';
        noCall.textContent = '— нет вызовов';
        diagramEl.appendChild(noCall);
      }
    });

    diagramEl.querySelectorAll('[data-element-id]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = el.getAttribute('data-element-id');
        if (id) showElementView(id);
      });
    });
  }

  detailsHeaderEl.innerHTML = '<span class="muted">Подсказка:</span> нажмите на метод или функцию, чтобы открыть уровень "Элемент".';
  codeBlockEl.textContent = '';
  updateNavigationButtons();
}

function showElementView(elementId) {
  currentView = 'element';
  currentElementId = elementId;

  const node = nodeById[elementId];
  if (!node) {
    levelKindEl.textContent = 'УРОВЕНЬ: ЭЛЕМЕНТ';
    levelTitleEl.textContent = `[${elementId}]`;
    diagramEl.innerHTML = '<div class="muted">Элемент не найден в графе.</div>';
    sidebarElementInfoEl.innerHTML = '';
    codeBlockEl.textContent = '';
    return;
  }

  const d = node.data || {};
  const moduleNode = getModuleForElementId(elementId);
  const filePath = moduleNode && moduleNode.data && moduleNode.data.path;
  const loc = d.loc || {};
  const startLine = loc.start_line || 1;
  const endLine = loc.end_line || startLine;

  levelKindEl.textContent = 'УРОВЕНЬ: ЭЛЕМЕНТ';
  levelTitleEl.textContent = `[${elementId}]`;

  const calls = getOutgoingCalls(elementId);
  const callsList = calls.map(c => `<li>${escapeHtml(c)}</li>`).join('');

  sidebarElementInfoEl.innerHTML = `
    <h4>Вызовы</h4>
    <ul>${callsList || '<li class="muted">нет</li>'}</ul>
  `;

  diagramEl.innerHTML = '';
  const h3 = document.createElement('h3');
  h3.textContent = elementId;
  diagramEl.appendChild(h3);

  const meta = document.createElement('div');
  meta.innerHTML = `
    <div><span class="tag">Файл</span> ${escapeHtml(filePath || 'неизвестно')}</div>
    <div><span class="tag">Строки</span> ${startLine}…${endLine}</div>
    <div style="margin-top:4px;">
      <span class="linkish" id="open-in-editor">Открыть в редакторе</span>
    </div>
  `;
  diagramEl.appendChild(meta);

  const openLink = meta.querySelector('#open-in-editor');
  if (openLink && filePath) {
    openLink.addEventListener('click', () => {
      vscode.postMessage({
        type: 'openLocation',
        file: filePath,
        line: startLine,
        col: 0
      });
    });
  }

  codeBlockEl.textContent = 'Загружаю код...';
  if (filePath) {
    vscode.postMessage({
      type: 'requestElementCode',
      id: elementId,
      file: filePath,
      startLine,
      endLine
    });
  } else {
    codeBlockEl.textContent = 'Файл для элемента не определён.';
  }
  updateNavigationButtons();
}

function renderElementCode(code, startLine) {
  if (!code) {
    codeBlockEl.textContent = 'Код не найден.';
    return;
  }
  const lines = String(code).split('\n');
  const withNums = lines.map((line, idx) => {
    const num = String(startLine + idx).padStart(4, ' ');
    return num + ' ' + line;
  });
  codeBlockEl.textContent = withNums.join('\n');
}


function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escapeAttr(str) {
  if (str == null) return '';
  return String(str).replace(/"/g, '&quot;');
}

function updateNavigationButtons() {
  const navButtonsEl = document.getElementById('navigation-buttons');
  navButtonsEl.innerHTML = '';

  if (currentView === 'module' || currentView === 'element') {
    const backToProjectBtn = document.createElement('button');
    backToProjectBtn.className = 'nav-btn';
    backToProjectBtn.textContent = '← К проекту';
    backToProjectBtn.onclick = () => {
      showProjectView();
      fileTreeEl.querySelectorAll('.tree-item').forEach(i => i.classList.remove('selected'));
      currentModulePath = null;
      currentElementId = null;
    };
    navButtonsEl.appendChild(backToProjectBtn);
  }

  if (currentView === 'element' && currentModulePath) {
    const backToModuleBtn = document.createElement('button');
    backToModuleBtn.className = 'nav-btn';
    backToModuleBtn.textContent = '← К модулю';
    backToModuleBtn.onclick = () => {
      selectTreeItem(currentModulePath);
      showModuleView(currentModulePath);
    };
    navButtonsEl.appendChild(backToModuleBtn);
  }

  navButtonsEl.style.display = navButtonsEl.children.length > 0 ? 'block' : 'none';
}