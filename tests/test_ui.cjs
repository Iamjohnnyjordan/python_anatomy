// DOM-independent smoke checks for the diagram's layout and reconstruction.
// Run: python -m unittest discover -s tests; node tests/test_ui.cjs
const fs = require('fs');
const vm = require('vm');
const {execFileSync} = require('child_process');
class Element {
  constructor() {this.style={setProperty(){}};this.classList={add(){},remove(){},toggle(){}};this.children=[];this.value='0';}
  setAttribute() {} append(...a) {this.children.push(...a);} replaceChildren(...a) {this.children=a;}
  addEventListener() {} querySelector() {return new Element();} scrollTo() {}
}
const examples = [fs.readFileSync('examples/mini_store.py','utf8'), 'products = ["Milk", "Bread", "Eggs"]', 'price = 2.99', 'x = ()', 'x = {}', 'x = {1, 2}', 'x = {"a": [1, True, None], "b": (2,)}', 'x = -3'];
async function run() {
  for (const source of examples) {
    const data = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-c', 'from backend.analyzer import analyze; import sys; print(analyze(sys.argv[1]).model_dump_json())', source], {encoding:'utf8'}));
    const elements = new Map();
    const get = id => {if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
    const context = {document:{getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element(),createTextNode:t=>t},fetch:async url=>url==='/examples/mini-store'?{ok:true,text:async()=>source}:{ok:true,json:async()=>data},requestAnimationFrame:()=>1,cancelAnimationFrame(){},performance:{now:()=>0},matchMedia:()=>({matches:false})};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync('frontend/app.js','utf8'), context);
    await new Promise(resolve => setImmediate(resolve));
    vm.runInContext(`
      if(!pieces.length) throw Error('No diagram');
      updateStage(1);
      if(revealOpacity(.2)!==0||revealOpacity(.5)!==1||revealOpacity(.35)<.49)throw Error('Unexpected label reveal timing');
      if(!overview && edges.length!==pieces.length-1) throw Error('Missing relationships');
      const height = parseFloat($('stage').style.height);
      for(const p of pieces) {
        if(!Number.isFinite(p.cx)||!Number.isFinite(p.cy)||p.cy+18>height) throw Error('Invalid or clipped position');
      }
      if(anatomy.root.kind==='assignment' && typeLabel(anatomy.root.children[0])!=='Variable name') throw Error('Missing beginner label');
      updateStage(0);
      if(pieces.some(p=>p.cx!==p.ax||p.cy!==p.ay)) throw Error('Reassembly failed');
      if(!overview && pieces.filter(p=>p.visibleAssembled).map(p=>p.el.textContent).sort().join('').length===0) throw Error('Empty assembled view');
      if(anatomy.root.kind==='module') {
        if(!$('structure-links').children.some(b=>b.textContent.startsWith('For loop · product')))throw Error('Missing direct for-loop navigation');
        if(!$('concept-groups').children.length)throw Error('Missing concept map');
        const conceptButtons=$('concept-groups').children.flatMap(group=>group.children[1].children);
        if(!conceptButtons.some(button=>button.textContent.startsWith('Class / object type')))throw Error('Class missing from concept map');
        if(!conceptButtons.some(button=>button.textContent.startsWith('Comment for the reader')))throw Error('Comments missing from concept map');
        $('hide-comments').checked=true;
        enter(anatomy.root);
        updateStage(1);
        if(pieces.some(piece=>piece.node.kind==='comment'))throw Error('Hide comments left a comment piece visible');
        if(pieces.some(piece=>piece.el.children.some(child=>(child.textContent||'').includes('# '))))throw Error('Hide comments left comment text in a code card');
        $('hide-comments').checked=false;
        const func=Array.from(nodeIndex.values()).find(n=>n.kind==='function');
        enter(func);
        if(viewRoot!==func||!overview)throw Error('Function navigation failed');
        const loop=Array.from(nodeIndex.values()).find(n=>n.kind==='while_loop');
        enter(loop);
        if(viewRoot!==loop)throw Error('Loop navigation failed');
        const assignment=Array.from(nodeIndex.values()).find(n=>n.kind==='assignment');
        enter(assignment);updateStage(1);
        if(overview)throw Error('Statement must explode into syntax');
        for(const kind of ['class','method','try_statement','with_statement','except_handler']) {
          const target=Array.from(nodeIndex.values()).find(n=>n.kind===kind);
          if(!target)throw Error('Missing new structure: '+kind);
          enter(target);updateStage(1);
          if(!overview)throw Error('Expected block overview: '+kind);
          if(pieces.some(p=>!Number.isFinite(p.cx)||!Number.isFinite(p.cy)))throw Error('Invalid block layout');
        }
        enter(anatomy.root);updateStage(0);
        if(!overview)throw Error('Return to whole program failed');
      }
    `,context);
  }
  console.log('Diagram smoke checks passed for 8 examples including whole-program navigation.');
}
run().catch(error => {console.error(error);process.exitCode=1;});
