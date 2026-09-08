const $ = id => document.getElementById(id);
const labels = {name:'Variable name', integer:'Whole number (int)', float:'Decimal number (float)', boolean:'True or False (bool)', none:'No value (None)', string:'Text (str)', assignment_operator:'Assignment operator', element:'Collection item', entry:'Dictionary entry', key_value_separator:'Key/value separator', sign_operator:'Number sign'};
const assignmentTypes = {dictionary:'Dictionary', list:'List', tuple:'Tuple', set:'Set', string:'Text', integer:'Whole-number', float:'Decimal-number', boolean:'Boolean', none:'None', call:'Call-result'};
Object.assign(labels, {class:'Class / object type', method:'Instance method', class_name:'Class name', default_value:'Default parameter value', keyword_argument_name:'Named argument', keyword_argument_separator:'Named-argument separator', with_statement:'Managed resource', try_statement:'Exception handling', except_handler:'Exception handler', exception_branch:'Exception branch', comment:'Comment for the reader', indentation:'Block indentation', augmented_assignment:'Update assignment', import_item:'Imported name', import_alias:'Import alias'});
labels.while_loop = 'While loop'; labels.for_loop = 'For loop'; labels.boolean_logic = 'Boolean logic'; labels.boolean_operator = 'Boolean operator';
const typeLabel = node => {
  if (node.kind === 'assignment') {
    const value = node.children.find(child => child.relationship === 'assigned value');
    return (assignmentTypes[value?.kind] ? assignmentTypes[value.kind] + ' assignment' : 'Assignment');
  }
  return labels[node.kind] || node.kind.replaceAll('_', ' ');
};

let anatomy;
let selected;
let selectedNode;
let viewRoot;
let nodeIndex = new Map();
let parentIndex = new Map();
let overview = false;
const conceptPositions = new Map();

function selectNode(node, button) {
  selected?.classList.remove('selected');
  selected?.setAttribute('aria-pressed', 'false');
  selected = button;
  selectedNode = node;
  button.classList.add('selected');
  button.setAttribute('aria-pressed', 'true');
  focusPieces(node.id);
  $('explore').disabled = !node.children.length;
  renderRelated(node);
  $('detail-title').textContent = node.label;
  $('kind').textContent = typeLabel(node);
  $('explanation').textContent = node.explanation;
  $('overview-steps').replaceChildren();
  $('overview-panel').hidden = !node.overview?.length;
  for (const step of node.overview || []) {
    const item = document.createElement('li'); item.textContent = step;
    $('overview-steps').append(item);
  }
  $('relationship').textContent = node.relationship + (parentIndex.get(node.id) ? ' · inside ' + parentIndex.get(node.id).label : '');
  const s = node.span;
  $('position').textContent = `Line ${s.start_line}, column ${s.start_column + 1} → line ${s.end_line}, column ${s.end_column + 1} (end exclusive)`;
  // Python offsets count Unicode code points; Array.from avoids UTF-16 slicing errors.
  const chars = Array.from(anatomy.source);
  const mark = document.createElement('mark');
  mark.textContent = chars.slice(s.start, s.end).join('');
  $('source-preview').replaceChildren(document.createTextNode(chars.slice(0, s.start).join('')), mark, document.createTextNode(chars.slice(s.end).join('')));
}
function renderNode(node) {
  const item = document.createElement('li');
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `node ${node.kind}`;
  button.setAttribute('aria-pressed', 'false');
  const label = document.createElement('span');
  label.textContent = node.label;
  const kind = document.createElement('small');
  kind.textContent = typeLabel(node);
  button.append(label, kind);
  button.addEventListener('click', () => selectNode(node, button));
  item.append(button);
  if (node.children.length) {
    const list = document.createElement('ul');
    node.children.forEach(child => list.append(renderNode(child)));
    item.append(list);
  }
  return item;
}
async function analyze() {
  $('analyze').disabled = true;
  $('status').textContent = 'Analyzing…';
  try {
    const response = await fetch('/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({source: $('source').value})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Enter source using 1–10,000 characters.');
    anatomy = data;
    nodeIndex = new Map(); parentIndex = new Map();
    function index(node, parent) {nodeIndex.set(node.id,node); if(parent)parentIndex.set(node.id,parent);node.children.forEach(child=>index(child,node));}
    index(data.root);
    renderConceptMap();
    viewRoot = data.root;
    renderBreadcrumbs();
    const list = document.createElement('ul');
    list.className = 'root';
    list.append(renderNode(data.root));
    $('tree').replaceChildren(list);
    buildStage();
    selectNode(data.root, list.querySelector('button'));
    $('status').textContent = 'Analysis ready. Select any component below.';
  } catch (error) {
    $('status').textContent = error.message;
    $('tree').replaceChildren();
    $('pieces').replaceChildren();
    $('connections').replaceChildren();
    cancelAnimationFrame(animation);
    pieces = []; edges = [];
    $('explode').disabled = true;
    $('explore').disabled = true; selectedNode = null;
    $('related').replaceChildren(); $('breadcrumbs').replaceChildren(); $('structure-links').replaceChildren(); $('concept-groups').replaceChildren(); $('structure-panel').hidden = true; $('concept-panel').hidden = true;
    $('detail-title').textContent = 'No analysis';
    $('explanation').textContent = 'Update your source and try again.';
    $('overview-panel').hidden = true; $('overview-steps').replaceChildren();
    for (const id of ['kind', 'relationship', 'position', 'source-preview']) $(id).textContent = '';
  } finally { $('analyze').disabled = false; }
}
$('form').addEventListener('submit', event => {event.preventDefault(); analyze();});
$('source').addEventListener('input', () => {$('status').textContent = 'Source edited. Press Analyze to update the anatomy.';});
// Each visual piece keeps the analyzer's identity while its position changes.
let pieces = [];
let edges = [];
let progress = 0;
let animation;
const svgNS = 'http://www.w3.org/2000/svg';
const labelRevealStart = 0.2;
const labelRevealEnd = 0.5;

function revealOpacity(value) {
  return Math.max(0, Math.min(1,
    (value - labelRevealStart) / (labelRevealEnd - labelRevealStart)));
}
function focusPieces(id) {
  const related = new Set([id]);
  for (const p of pieces) if (p.node.id === id || p.parent === id) {
    related.add(p.node.id); related.add(p.parent);
  }
  for (const p of pieces) p.el.classList.toggle('dimmed', id !== viewRoot.id && !related.has(p.node.id));
}
function buildStage() {
  overview = ['module','class','method','function','for_loop','while_loop','if_statement','try_statement','except_handler','exception_branch','with_statement'].includes(viewRoot.kind);
  if (overview) {buildOverview(); return;}
  cancelAnimationFrame(animation);
  pieces = []; edges = [];
  $('pieces').replaceChildren(); $('connections').replaceChildren();
  $('explode').disabled = false; $('explode').value = 0;
  const source = Array.from(anatomy.source);
  let cursor = 40;
  function visit(node, depth, parent) {
    const el = document.createElement('button');
    el.type = 'button'; el.className = `piece ${node.kind}`;
    el.setAttribute('aria-pressed', 'false');
    el.setAttribute('aria-label', `${typeLabel(node)}: ${node.label}`);
    // The string body and its quote children together reconstruct its source literal.
    const text = node.kind === 'indentation' ? '·'.repeat(node.span.end-node.span.start) : node.kind === 'string' ? source.slice(node.span.start + 1, node.span.end - 1).join('') : node.label;
    el.textContent = text;
    el.title = node.explanation;
    el.addEventListener('click', () => selectNode(node, el));
    el.addEventListener('dblclick', () => {if(node.children.length)enter(node);});
    $('pieces').append(el);
    const width = Math.max(30, Array.from(text).length * 10 + 22);
    const p = {node, parent, depth, el, width};
    pieces.push(p);
    const subtreeStart = cursor;
    const kids = node.children
      .filter(child => !$('hide-comments').checked || child.kind !== 'comment')
      .map(child => visit(child, depth + 1, node.id));
    if (kids.length) p.x = (kids[0].x + kids[kids.length - 1].x) / 2;
    else {p.x = cursor + width / 2; cursor += width + 35;}
    // A string body needs its own room between the quote leaves.
    if (node.kind === 'string') {
      const extra = width + 24;
      kids[1].x += extra; cursor += extra;
      p.x = (kids[0].x + kids[1].x) / 2;
    }
    if (kids.length && cursor - subtreeStart < width + 35) {
      const extra = width + 35 - (cursor - subtreeStart);
      const subtree = pieces.slice(pieces.indexOf(p));
      for (const part of subtree) part.x += extra / 2;
      cursor += extra;
    }
    p.y = 55 + depth * 100;
    const start = source.slice(0, node.span.start);
    const line = start.lastIndexOf('\n');
    p.ax = 40 + (start.length - line - 1) * 10 + (node.kind === 'string' ? 10 : 0) + (width - 22) / 2;
    p.ay = 235 + (node.span.start_line - viewRoot.span.start_line) * 30;
    p.visibleAssembled = (node.children.length === 0 && node.kind !== 'indentation') || node.kind === 'string';
    return p;
  }
  visit(viewRoot, 0, null);
  const width = Math.max(680, cursor + 40, ...pieces.map(p => Math.max(p.ax, p.x) + p.width));
  const height = Math.max(640, ...pieces.map(p => Math.max(p.ay, p.y) + 70));
  $('stage').style.width = `${width}px`; $('stage').style.height = `${height}px`;
  $('connections').setAttribute('width', width); $('connections').setAttribute('height', height);
  const byId = new Map(pieces.map(p => [p.node.id, p]));
  for (const p of pieces) if (p.parent) {
    const line = document.createElementNS(svgNS, 'path');
    $('connections').append(line); edges.push({line, a: byId.get(p.parent), b:p});
  }
  updateStage(0);
}
function updateStage(value) {
  if(overview) {updateOverview(value); return;}
  progress = value; $('amount').textContent = `${Math.round(value * 100)}%`;
  for (const p of pieces) {
    p.cx = p.ax + (p.x - p.ax) * value;
    p.cy = p.ay + (p.y - p.ay) * value;
    p.el.style.left = `${p.cx}px`; p.el.style.top = `${p.cy}px`;
    const labelOpacity = revealOpacity(value);
    p.el.style.opacity = p.visibleAssembled ? 1 : labelOpacity;
    p.el.style.pointerEvents = !p.visibleAssembled && value <= labelRevealStart ? 'none' : 'auto';
    p.el.tabIndex = !p.visibleAssembled && value <= labelRevealStart ? -1 : 0;
    p.el.style.setProperty('--separation', value);
  }
  for (const {line,a,b} of edges) {
    line.setAttribute('d', `M ${a.cx} ${a.cy+18} C ${a.cx} ${(a.cy+b.cy)/2}, ${b.cx} ${(a.cy+b.cy)/2}, ${b.cx} ${b.cy-18}`);
    line.style.opacity = value * .65;
  }
}
$('explode').addEventListener('input', () => {cancelAnimationFrame(animation); updateStage(Number($('explode').value)/100);});
$('hide-comments').addEventListener('change', rebuildCurrentView);

function rebuildCurrentView() {
  const previousProgress = progress;
  buildStage();
  $('explode').value = previousProgress * 100;
  updateStage(previousProgress);
  if (selectedNode && selectedNode.kind !== 'comment') {
    const visual = pieces.find(piece => piece.node.id === selectedNode.id);
    if (visual) selectNode(selectedNode, visual.el);
  }
}
$('reassemble').addEventListener('click', () => {
  cancelAnimationFrame(animation);
  const from = progress, start = performance.now();
  const duration = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 650;
  function frame(now) {
    const t = duration ? Math.min(1, (now-start)/duration) : 1;
    const value = from * (1-t)*(1-t)*(1-t);
    $('explode').value = value*100; updateStage(value);
    if(t<1) animation = requestAnimationFrame(frame);
    else $('viewport').scrollTo({left:0,top:0});
  }
  animation = requestAnimationFrame(frame);
});
const examples = {
  store: 'import json\nfrom math import ceil as round_up\n\n# Data for our store: text, numbers, collections, and optional values.\nprices = {"Milk": 2.99, "Bread": 1.50, "Eggs": 3.25}\ncategories = {"Dairy", "Bakery"}\nstore_location = (2, 4)\ndiscount = None\nstore_open = True\n\n# This for loop runs directly in the program, without a def.\nfor product in prices:\n    print(product, prices[product])\n\nrequests = ["Milk", "", "Bread", "Soap", "CHECKOUT", "Eggs"]\ncart = []\nposition = 0\n\nwhile store_open and position < len(requests):\n    product = requests[position]\n    position += 1\n    if not product:\n        continue\n    if product == "CHECKOUT" or product == "QUIT":\n        break\n    if product not in prices:\n        continue\n    cart.append(product)\n\n\ndef calculate_total(items, price_list):\n    total = 0.0\n    # This for loop is inside a function; both kinds remain in the program.\n    for product in items:\n        if product in price_list:\n            total = total + price_list[product]\n    return total\n\n\ndef ask_customer(default_name="Guest"):\n    name = input("Your name: ")\n    if not name:\n        return default_name\n    return name\n\n\nclass Receipt:\n    def __init__(self, items, total):\n        self.items = items\n        self.total = total\n\n    def show(self):\n        print("Items:", self.items)\n        print("Total:", self.total)\n\n    def save(self, filename="receipt.json"):\n        if not self.items:\n            raise ValueError("Cannot save an empty receipt")\n        payload = {"items": self.items, "total": self.total}\n        with open(filename, "w", encoding="utf-8") as file:\n            json.dump(payload, file)\n        with open(filename, "r", encoding="utf-8") as file:\n            saved_text = file.read()\n        return saved_text\n\n\nsubtotal = calculate_total(cart, prices)\nif discount is not None:\n    subtotal = subtotal - discount\nelif subtotal > 0:\n    print("No discount applied")\nelse:\n    print("Your cart is empty")\n\nrounded_total = round_up(subtotal)\nreceipt = Receipt(cart, subtotal)\nreceipt.show()\nprint("Rounded up:", rounded_total)\nprint("Store location:", store_location)\nprint("Categories:", categories)\n\n# Analyzing this example does not execute it or create a file.\ntry:\n    saved = receipt.save(filename="receipt.json")\nexcept (OSError, ValueError) as error:\n    print("Receipt could not be saved:", error)\nelse:\n    print("Saved receipt:", saved)\nfinally:\n    print("Checkout finished")\n',
  products: 'products = ["Milk", "Bread", "Eggs"]',
  integer: 'quantity = 3',
  float: 'price = 2.99',
  boolean: 'in_stock = True',
  none: 'discount = None',
  tuple: 'location = (2, 4)',
  dictionary: 'prices = {"Milk": 2.99, "Bread": 1.50}',
  set: 'categories = {"Dairy", "Bakery"}',
  nested: 'product = {"name": "Milk", "prices": [2.99, 3.49], "in_stock": True}'
};
$('example').addEventListener('change', () => {
  $('source').value = examples[$('example').value];
  analyze();
});

function renderStructureLinks() {
  $('structure-links').replaceChildren();
  const kinds = {module:'Whole program', class:'Class', method:'Method', function:'Function', for_loop:'For loop', while_loop:'While loop', try_statement:'Try / exceptions', except_handler:'Except handler', with_statement:'With / resource'};
  for (const node of nodeIndex.values()) {
    if (!kinds[node.kind]) continue;
    const button = document.createElement('button'); button.type = 'button';
    const name = ['function','method','class'].includes(node.kind) ? node.label.replace(/^(Function|Method|Class) /, '') : node.kind === 'for_loop' ? node.label.replace(/^For each /, '') : '';
    button.textContent = kinds[node.kind] + (name ? ' · ' + name : '') + ' · line ' + node.span.start_line;
    if (node.id === viewRoot.id) button.setAttribute('aria-current', 'location');
    button.addEventListener('click', () => enter(node));
    $('structure-links').append(button);
  }
  $('structure-panel').hidden = !Array.from(nodeIndex.values()).some(node => kinds[node.kind]);
}

function renderConceptMap() {
  const groups = [
    ['Program parts', ['module','import','class','method','function']],
    ['Flow and decisions', ['for_loop','while_loop','if_statement','break','continue','return','try_statement','except_handler','with_statement','raise']],
    ['Values and collections', ['assignment','augmented_assignment','name','dictionary','list','tuple','set','string','integer','float','boolean','none']],
    ['Expressions and inputs', ['call','argument','parameter','attribute','lookup','calculation','comparison','boolean_logic']],
    ['Written syntax', ['comment','indentation','syntax','assignment_operator','separator','quote']]
  ];
  const byKind = new Map();
  for (const node of nodeIndex.values()) {
    if (!byKind.has(node.kind)) byKind.set(node.kind, []);
    byKind.get(node.kind).push(node);
  }
  conceptPositions.clear();
  $('concept-groups').replaceChildren();
  for (const [heading, kinds] of groups) {
    const present = kinds.filter(kind => byKind.has(kind));
    if (!present.length) continue;
    const group = document.createElement('section');
    const title = document.createElement('h4'); title.textContent = heading;
    const links = document.createElement('div'); links.className = 'concept-links';
    for (const kind of present) {
      const nodes = byKind.get(kind);
      const button = document.createElement('button'); button.type = 'button';
      const update = index => {
        const position = nodes.length > 1 ? ` · ${index + 1}/${nodes.length}` : '';
        button.textContent = `${typeLabel(nodes[index])}${position}`;
      };
      update(0);
      button.addEventListener('click', () => {
        const index = conceptPositions.get(kind) || 0;
        jumpToNode(nodes[index], button);
        const next = (index + 1) % nodes.length;
        conceptPositions.set(kind, next);
        update(next);
      });
      links.append(button);
    }
    group.append(title, links);
    $('concept-groups').append(group);
  }
  $('concept-panel').hidden = !$('concept-groups').children.length;
}

function jumpToNode(node, fallbackButton) {
  if (node.children.length) {
    enter(node);
    return;
  }
  const container = parentIndex.get(node.id) || anatomy.root;
  enter(container);
  const visual = pieces.find(piece => piece.node.id === node.id);
  selectNode(node, visual?.el || fallbackButton);
}

function renderBreadcrumbs() {
  renderStructureLinks();
  const path = []; let node = viewRoot;
  while(node) {path.unshift(node);node = parentIndex.get(node.id);}
  $('breadcrumbs').replaceChildren();
  for(const item of path) {
    const button = document.createElement('button'); button.type='button';
    button.textContent = item.label; button.addEventListener('click',()=>enter(item));
    if(item.id===viewRoot.id)button.setAttribute('aria-current','location');
    $('breadcrumbs').append(button);
  }
}
function enter(node) {
  viewRoot=node; renderBreadcrumbs(); buildStage();
  $('viewport').scrollTo({left:0,top:0});
  selectNode(node, document.createElement('button'));
}
function descendants(node) {
  const ids=new Set();
  function visit(n){ids.add(n.id);n.children.forEach(visit);} visit(node);return ids;
}
function renderRelated(node) {
  $('related').replaceChildren();
  const ids=descendants(node), seen=new Set();
  for(const edge of anatomy.connections || []) {
    const from=ids.has(edge.source_id), to=ids.has(edge.target_id);
    if(!from&&!to)continue;
    const other=nodeIndex.get(from?edge.target_id:edge.source_id);
    if(!other||seen.has(other.id))continue;
    seen.add(other.id);
    const button=document.createElement('button');button.type='button';
    button.textContent=edge.label.includes('this loop') ? `${edge.label} · line ${other.span.start_line}: ${other.label}` : `${from?'Used':'Defined'} at line ${other.span.start_line}: ${other.label}`;
    button.title=edge.label;
    button.addEventListener('click',()=>{enter(parentIndex.get(other.id)||other);selectNode(other,button);});
    $('related').append(button);
  }
  if(!seen.size)$('related').textContent='No name-binding connections found for this piece.';
}
$('explore').addEventListener('click',()=>{if(selectedNode?.children.length)enter(selectedNode);});
$('zoom').addEventListener('input',()=>{
  $('stage').style.zoom=Number($('zoom').value)/100;
  $('zoom-label').textContent=$('zoom').value+'%';
});
function buildOverview() {
  cancelAnimationFrame(animation);pieces=[];edges=[];
  $('pieces').replaceChildren();$('connections').replaceChildren();
  $('explode').disabled=false;$('explode').value=0;
  const source=Array.from(anatomy.source);
  const comments=Array.from(nodeIndex.values()).filter(node=>node.kind==='comment');
  function sourceForView(start,end) {
    const visible=source.slice(start,end);
    if ($('hide-comments').checked) {
      for (const comment of comments) {
        const from=Math.max(start,comment.span.start);
        const to=Math.min(end,comment.span.end);
        for(let index=from;index<to;index++) visible[index-start]=' ';
      }
    }
    return visible.join('').replace(/[ \t]+(?=\n)/g,'');
  }
  const children=viewRoot.children.filter(node => node.kind !== 'indentation' &&
    (!$('hide-comments').checked || node.kind !== 'comment'));
  let rowY=70, rowHeight=0;
  children.forEach((node,i)=>{
    const raw=sourceForView(node.span.start,node.span.end);
    const lines=raw.split('\n');
    // Remove the common block indentation after the first line when focusing inward.
    const display=lines.map((line,j)=>j?line.slice(Math.min(node.span.start_column,line.search(/\S|$/))):line).join('\n');
    const height=Math.max(65,lines.length*22+36);
    const aw=Math.max(12,...display.split('\n').map(line=>Array.from(line).length*9+2));
    const width=Math.max(410,aw+28);
    if(i%2===0&&i>0){rowY+=rowHeight+60;rowHeight=0;}
    const el=document.createElement('button');el.type='button';el.className='program-piece';
    const title=document.createElement('span');title.className='piece-heading';title.textContent=typeLabel(node)+' · '+(node.kind==='assignment' ? node.label.replace(/^Assign /,'') : node.label);
    const code=document.createElement('code');code.textContent=display;
    el.append(title,code);el.setAttribute('aria-pressed','false');
    el.addEventListener('click',()=>selectNode(node,el));
    el.addEventListener('dblclick',()=>{if(node.children.length)enter(node);});
    $('pieces').append(el);
    pieces.push({node,el,width,aw,height,title,ids:descendants(node), ax:30+(node.span.start_column-viewRoot.span.start_column)*9,ay:45+(node.span.start_line-viewRoot.span.start_line)*22,x:35+(i%2)*650,y:rowY,visibleAssembled:true});
    rowHeight=Math.max(rowHeight,height);
  });
  // Put the second column beyond the widest first-column card.
  const columnWidth=Math.max(600,...pieces.filter((_,i)=>i%2===0).map(p=>p.width+60));
  pieces.forEach((p,i)=>{if(i%2)p.x=35+columnWidth;});
  const width=Math.max(760,...pieces.map(p=>Math.max(p.ax,p.x)+p.width+50));
  const height=Math.max(640,...pieces.map(p=>Math.max(p.ay,p.y)+p.height+70));
  $('stage').style.width=width+'px';$('stage').style.height=height+'px';
  $('connections').setAttribute('width',width);$('connections').setAttribute('height',height);
  const seen=new Set();
  for(const edge of anatomy.connections||[]) {
    const a=pieces.find(p=>p.ids.has(edge.source_id)),b=pieces.find(p=>p.ids.has(edge.target_id));
    if(!a||!b||a===b)continue;
    const key=a.node.id+':'+b.node.id;if(seen.has(key))continue;seen.add(key);
    const line=document.createElementNS(svgNS,'path');line.classList.add('binding-line');
    $('connections').append(line);edges.push({line,a,b});
  }
  updateOverview(0);
}
function updateOverview(value) {
  progress=value;$('amount').textContent=Math.round(value*100)+'%';
  for(const p of pieces) {
    p.cx=p.ax+(p.x-p.ax)*value;p.cy=p.ay+(p.y-p.ay)*value;
    p.el.style.left=p.cx+'px';p.el.style.top=p.cy+'px';p.el.style.width=(p.aw+(p.width-p.aw)*value)+'px';
    p.el.style.setProperty('--separation',value);
    p.title.style.opacity=revealOpacity(value);
  }
  for(const {line,a,b} of edges) {
    line.setAttribute('d',`M ${a.cx+a.width/2} ${a.cy+25} Q ${(a.cx+b.cx)/2} ${Math.min(a.cy,b.cy)-30} ${b.cx+b.width/2} ${b.cy+25}`);
    line.style.opacity=value*.8;
  }
}

async function loadInitialExample() {
  try {
    const response = await fetch('/examples/mini-store');
    if (!response.ok) throw new Error('The guided store example could not be loaded.');
    examples.store = await response.text();
    $('source').value = examples.store;
  } catch (error) {
    // The embedded source remains a usable fallback if this optional request fails.
    $('status').textContent = error.message;
  }
  analyze();
}

loadInitialExample();
