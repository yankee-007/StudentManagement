// Headless check of the class-169 preview page: DOM stub + real ECharts render.
const fs = require('fs');
const path = require('path');
const target = process.argv[2] || path.join(__dirname, 'dashboard-169.html');
const html = fs.readFileSync(target, 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (scripts.length < 2) { console.error('FAIL: expected 2 inline scripts, got ' + scripts.length); process.exit(1); }

function makeEl(id) {
  const node = { id, style: {}, dataset: {}, children: [], value: '0', selected: false,
    appendChild(c) { this.children.push(c); return c; }, removeChild() {}, insertBefore() {},
    addEventListener() {}, removeEventListener() {}, setAttribute() {}, removeAttribute() {},
    getAttribute: () => null, setAttributeNS() {}, removeAttributeNS() {},
    getBoundingClientRect: () => ({left: 0, top: 0, width: 700, height: 330}) };
  return new Proxy(node, {
    get(target, prop) {
      if (prop in target) return target[prop];
      if (typeof prop === 'string') { target[prop] = () => undefined; return target[prop]; }
      return undefined;
    },
    set(target, prop, value) { target[prop] = value; return true; }
  });
}
const ids = ['cards', 'bands', 'baseline', 'detail', 'foot', 'classPill', 'total', 'total2', 'gradeBadge',
             'chart-rate', 'chart-funnel', 'chart-bottom', 'chart-trend'];
const elements = {};
ids.forEach(id => elements[id] = makeEl(id));
const buttons = [];
const doc = {
  getElementById: (id) => elements[id] || (elements[id] = makeEl(id)),
  querySelector: () => buttons.find(b => b.classList && b.classList.has && b.classList.has('on')) || buttons[0] || null,
  querySelectorAll: (sel) => sel.includes('data-tab') ? buttons.filter(b => b.dataset.tab) : buttons.filter(b => b.dataset.trend),
  createElement: () => makeEl('opt'),
  createElementNS: (ns, name) => makeEl(name)
};
global.document = new Proxy(doc, {
  get(target, prop) {
    if (prop in target) return target[prop];
    if (prop === 'createTextNode') return () => makeEl('#text');
    if (prop === 'body' || prop === 'documentElement') return makeEl(String(prop));
    if (typeof prop === 'string') { target[prop] = (() => makeEl(String(prop))); return target[prop]; }
    return undefined;
  }
});
global.window = { addEventListener() {} };
global.navigator = { userAgent: 'node' };

// toolbar buttons from the real markup
for (const m of html.matchAll(/<button[^>]*data-(tab|trend)="([^"]+)"[^>]*>/g)) {
  const on = /class="on"/.test(m[0]);
  const set = new Set(on ? ['on'] : []);
  buttons.push({ dataset: {[m[1]]: m[2]}, classList: {add: (c) => set.add(c), remove: (c) => set.delete(c), has: (c) => set.has(c)},
                 set onclick(fn) { this._fn = fn; } });
}

const echarts = require(path.join(__dirname, '..', 'vendor', 'echarts.min.js'));
const charts = [];
global.echarts = Object.assign({}, echarts, { init: (el) => {
  const chart = echarts.init(el, null, { renderer: 'svg', width: 700, height: 330 });
  charts.push(chart); return chart;
}});

try { new Function(scripts[1])(); }
catch (err) { console.error('FAIL: page script threw ->', err.message); console.error(err.stack); process.exit(1); }

console.log('page:', target);
console.log('charts:', charts.length);
charts.forEach((c, i) => {
  const o = c.getOption();
  console.log('  #' + i, (o.series || []).map(s => s.name + '(' + (s.data || []).length + ')').join(', '),
              '| dataZoom', (o.dataZoom || []).length, '| yAxis', (o.yAxis || []).length);
});
const gapSeries = charts[2].getOption().series[0].data;
const markLine = charts[2].getOption().series[0].markLine;
const marks = (Array.isArray(markLine) ? markLine[0].data : (markLine && markLine.data)) || [];
const data = JSON.parse(html.match(/const DATA = (\{[\s\S]*?\});/)[1]);
console.log('lessons:', data.lessonsList.join(','), '| open', data.openLessons, 'of', data.targetLessons, '| total', data.total);
console.log('gap per lesson:', gapSeries.join(', '));
console.log('grades:', JSON.stringify(data.gradeCounts), '|', data.gradeSummary);
console.log('expected points per series:', data.openLessons);
const sizes = new Set(charts[0].getOption().series.map(s => s.data.length));
console.log('series point counts:', [...sizes].join(','), sizes.size === 1 && sizes.has(data.openLessons) ? 'OK' : 'FAIL');
console.log('markLine thresholds:', marks.map(m => m.yAxis).join(','));
const funnel = charts[1].getOption().series;
const totals = funnel[0].data.map((v, i) => v + funnel[1].data[i] + funnel[2].data[i]);
console.log('funnel totals unique:', [...new Set(totals)].join(','));
console.log('badge:', elements['gradeBadge'].textContent, '| cards len:', (elements['cards'].innerHTML || '').length);
console.log('bands:', (elements['bands'].innerHTML || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 150));
console.log('options:', elements['baseline'].children.map(o => o.textContent).join(' | '));
console.log('detail:', (elements['detail'].innerHTML || '').replace(/<[^>]+>/g, '').slice(0, 120));
console.log(totals.every(t => t === 171) ? 'OK: 堆叠合计恒等于 171' : 'FAIL: 堆叠合计不等于 171');
