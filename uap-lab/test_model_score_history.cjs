const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'static/observation-metrics.js'),'utf8');const context={};vm.createContext(context);vm.runInContext(source.slice(source.indexOf('function modelComposite'),source.indexOf('\n(()=>{')),context);const score=context.modelComposite;
assert.equal(score({tp:10,tn:10,fp:0,fn:0}).score,100);
assert.equal(score({tp:0,tn:10,fp:1,fn:10}).score,0);
for(const counts of [{tp:0,tn:10,fp:0,fn:0},{tp:10,tn:0,fp:0,fn:0},{tp:NaN,tn:10,fp:2,fn:3},{}])assert.equal(score(counts),null);
const c={tp:80,tn:90,fp:10,fn:20};const expected=100/(.35/.8+.25/(80/90)+.25/.9+.15/.85);assert.equal(score(c).score,Math.round(expected*10)/10);
console.log('PASS: score history uses the leaderboard composite, missing support is unscored, zero stays zero');
