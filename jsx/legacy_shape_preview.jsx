/* Standalone ExtendScript transaction. Never called from executeAsModal. */
(function () {
    var request = __PS_MENU_LEGACY_REQUEST__;
    var s = stringIDToTypeID, c = charIDToTypeID, prepared = request.prepared;
    var doc = null, anchor = null, result, changed = false;
    var originalHistory = null, historyStarted = false,stage='capture-target';
    var folder = new Folder(request.folder), mailbox = new File(folder + '/mask-preview-' + request.id + '.json');
    var receipt = new File(folder + '/legacy-result-' + request.id + '.json');
    function encode(value) {
        if (value === null) return 'null';
        if (typeof value === 'string') return '"' + value.replace(/["\\\x00-\x1f]/g, function (v) {
            var n = v.charCodeAt(0).toString(16); return '\\u' + ('0000' + n).slice(-4);
        }) + '"';
        if (typeof value === 'number') { if (!isFinite(value)) throw Error('Nonfinite value'); return String(value); }
        if (typeof value === 'boolean') return String(value);
        var out = [], i, keys = [];
        if (value instanceof Array) { for (i = 0; i < value.length; i++) out.push(encode(value[i])); return '[' + out.join(',') + ']'; }
        for (i in value) if (value.hasOwnProperty(i) && typeof value[i] !== 'undefined') keys.push(i);
        keys.sort(); for (i = 0; i < keys.length; i++) out.push(encode(keys[i]) + ':' + encode(value[keys[i]]));
        return '{' + out.join(',') + '}';
    }
    // Parse mailbox data, never eval it. Bound size, depth, duplicate keys and numbers.
    function decode(text) {
        if (text.length > 4096) throw Error('Mailbox size limit');
        var at = 0;
        function ws() { while (/\s/.test(text.charAt(at)) && at < text.length) at++; }
        function str() {
            if (text.charAt(at++) !== '"') throw Error('String expected');
            var out = '', ch, hex, map = {'"':'"','\\':'\\','/':'/','b':'\b','f':'\f','n':'\n','r':'\r','t':'\t'};
            while (at < text.length) {
                ch = text.charAt(at++); if (ch === '"') return out;
                if (ch === '\\') {
                    ch = text.charAt(at++);
                    if (ch === 'u') { hex = text.substr(at, 4); if (!/^[a-fA-F0-9]{4}$/.test(hex)) throw Error('Invalid escape'); at += 4; out += String.fromCharCode(parseInt(hex, 16)); }
                    else if (map.hasOwnProperty(ch)) out += map[ch]; else throw Error('Invalid escape');
                } else { if (ch.charCodeAt(0) < 32) throw Error('Control character'); out += ch; }
            }
            throw Error('Unclosed string');
        }
        function value(depth) {
            if (depth > 16) throw Error('JSON depth limit'); ws();
            var ch = text.charAt(at), out, key, match;
            if (ch === '"') return str();
            if (ch === '{' || ch === '[') {
                at++; out = ch === '{' ? {} : []; ws();
                if (text.charAt(at) === (ch === '{' ? '}' : ']')) { at++; return out; }
                while (true) {
                    ws(); if (ch === '{') {
                        key = str(); if (/^(?:__proto__|constructor|prototype)$/.test(key) || out.hasOwnProperty(key)) throw Error('Invalid object key');
                        ws(); if (text.charAt(at++) !== ':') throw Error('Colon expected'); out[key] = value(depth + 1);
                    } else out.push(value(depth + 1));
                    ws(); key = text.charAt(at++); if (key === (ch === '{' ? '}' : ']')) return out;
                    if (key !== ',') throw Error('Separator expected');
                }
            }
            match = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(text.slice(at));
            if (!match) throw Error('Invalid JSON value'); at += match[0].length;
            if (match[0] === 'true') return true; if (match[0] === 'false') return false; if (match[0] === 'null') return null;
            out = Number(match[0]); if (!isFinite(out)) throw Error('Nonfinite number'); return out;
        }
        var out = value(0); ws(); if (at !== text.length) throw Error('Trailing JSON'); return out;
    }
    function same(a, b) { return encode(a) === encode(b); }
    function unit(id) {
        if (id === c('#Pxl')) return 'pixelsUnit'; if (id === c('#Prc')) return 'percentUnit';
        if (id === c('#Ang')) return 'angleUnit'; if (id === c('#Pnt')) return 'pointsUnit';
        return typeIDToStringID(id) || typeIDToCharID(id);
    }
    function name(id) { return typeIDToStringID(id) || typeIDToCharID(id); }
    function object(d) {
        var out = {}, i, k; for (i = 0; i < d.count; i++) { k = d.getKey(i); out[name(k)] = item(d, k); } return out;
    }
    function item(d, k) {
        var t = d.getType(k), out, i;
        if (t === DescValueType.OBJECTTYPE) { out = object(d.getObjectValue(k)); out._obj = name(d.getObjectType(k)); return out; }
        if (t === DescValueType.LISTTYPE) { out = []; var list = d.getList(k); for (i = 0; i < list.count; i++) out.push(item(list, i)); return out; }
        if (t === DescValueType.ENUMERATEDTYPE) return {_enum:name(d.getEnumerationType(k)), _value:name(d.getEnumerationValue(k))};
        if (t === DescValueType.UNITDOUBLE) return {_unit:unit(d.getUnitDoubleType(k)), _value:d.getUnitDoubleValue(k)};
        if (t === DescValueType.DOUBLETYPE) return d.getDouble(k);
        if (t === DescValueType.INTEGERTYPE) return d.getInteger(k);
        if (t === DescValueType.BOOLEANTYPE) return d.getBoolean(k);
        if (t === DescValueType.STRINGTYPE) return d.getString(k);
        throw Error('Unsupported style descriptor');
    }
    function layerDescriptor() { var r = new ActionReference(); r.putIdentifier(c('Lyr '), anchor.id); return executeActionGet(r); }
    function clone(d) { var copy = new ActionDescriptor(); copy.fromStream(d.toStream()); return copy; }
    function pathStream() { if (!prepared.raw.vector) return null; var r = new ActionReference(); r.putEnumerated(s('path'), s('path'), s('vectorMask')); return executeActionGet(r).toStream(); }
    function mask(d) { return {feather:d.getDouble(s('vectorMaskFeather')), density:d.getInteger(s('vectorMaskDensity')) * 100 / 255}; }
    function maskClose(a, b) { return Math.abs(a.feather - b.feather) < .01 && Math.abs(a.density - b.density) <= 100 / 255 + .001; }
    function raw(d) {
        var fillList = d.getList(s('adjustment')), fill = object(fillList.getObjectValue(0)); fill._obj = name(fillList.getObjectType(0));
        var stroke = prepared.raw.stroke;
        if (d.hasKey(s('AGMStrokeStyleInfo'))) { stroke = object(d.getObjectValue(s('AGMStrokeStyleInfo'))); stroke._obj = name(d.getObjectType(s('AGMStrokeStyleInfo'))); }
        return {fill:fill, stroke:stroke, vector:d.hasKey(s('hasVectorMask')) && d.getBoolean(s('hasVectorMask'))};
    }
    function selected() {
        var r = new ActionReference(); r.putProperty(c('Prpr'), s('targetLayersIDs')); r.putEnumerated(c('Dcmn'), c('Ordn'), c('Trgt'));
        var d = executeActionGet(r), list = d.getList(s('targetLayersIDs')), ids = [], i;
        for (i = 0; i < list.count; i++) ids.push(list.getReference(i).getIdentifier()); return ids;
    }
    function target() {
        if (app.activeDocument.id !== request.target.document_id || anchor.id !== request.target.active_layer_id || doc.activeLayer.id !== anchor.id || selected().join(',') !== String(anchor.id)) throw Error('Preview target changed');
        var layer = anchor; while (layer.typename === 'ArtLayer' || layer.typename === 'LayerSet') { if (layer.allLocked) throw Error('Preview target locked'); layer = layer.parent; }
    }
    function order() { var out = [], layers = anchor.parent.layers, i; for (i = 0; i < layers.length; i++) out.push(layers[i].id); return out; }
    function parentID() { return anchor.parent.typename === 'LayerSet' ? anchor.parent.id : null; }
    function pixelMask(d) { return {exists:d.hasKey(s('hasUserMask')) && d.getBoolean(s('hasUserMask')), feather:d.hasKey(s('userMaskFeather')) ? d.getDouble(s('userMaskFeather')) : null, density:d.hasKey(s('userMaskDensity')) ? d.getInteger(s('userMaskDensity')) : null}; }
    function rgb(d) { return [d.getDouble(s('red')), d.getDouble(s('grain')), d.getDouble(s('blue'))]; }
    function paint(d, type) {
        if (type === s('solidColorLayer')) return {kind:'solid', rgb:rgb(d.getObjectValue(c('Clr ')))};
        if (type === s('patternLayer')) return {kind:'pattern', name:d.getObjectValue(s('pattern')).getString(c('Nm  '))};
        if (type !== s('gradientLayer')) throw Error('Unsupported paint kind');
        var colors = d.getObjectValue(s('gradient')).getList(s('colors')), stops = [], i, stop;
        for (i = 0; i < colors.count; i++) { stop = colors.getObjectValue(i); stops.push({rgb:rgb(stop.getObjectValue(c('Clr '))), location:stop.getInteger(s('location'))}); }
        return {kind:'gradient', stops:stops};
    }
    function samePaint(actual, wanted) {
        if (actual.kind !== wanted.kind) return false;
        function colors(a, b) { return Math.abs(a[0]-b[0])<=1 && Math.abs(a[1]-b[1])<=1 && Math.abs(a[2]-b[2])<=1; }
        if (actual.kind === 'solid') return colors(actual.rgb, wanted.rgb);
        if (actual.kind === 'pattern') return actual.name === wanted.name;
        if (actual.stops.length !== wanted.stops.length) return false;
        for (var i = 0; i < actual.stops.length; i++) if (actual.stops[i].location !== wanted.stops[i].location || !colors(actual.stops[i].rgb, wanted.stops[i].rgb)) return false;
        return true;
    }
    function validate(p) {
        if (!p || p.revision !== request.paint.revision || typeof p.fill !== 'object' || typeof p.stroke !== 'object' || (p.hasOwnProperty('mask') !== request.paint.hasOwnProperty('mask'))) throw Error('Preview revision changed');
        function color(v) { return v instanceof Array && v.length === 3 && range(v[0],0,255) && range(v[1],0,255) && range(v[2],0,255); }
        function one(v) {
            if (!v || typeof v.enabled !== 'boolean') throw Error('Invalid paint');
            if (v.kind === 'solid') { if (!color(v.rgb)) throw Error('Invalid RGB'); }
            else if (v.kind === 'gradient') {
                if (!(v.stops instanceof Array) || v.stops.length < 2 || v.stops.length > 32) throw Error('Invalid gradient');
                for (var i=0;i<v.stops.length;i++) if (!color(v.stops[i].rgb) || !range(v.stops[i].location,0,4096) || Math.floor(v.stops[i].location)!==v.stops[i].location || i && v.stops[i].location<v.stops[i-1].location) throw Error('Invalid gradient stop');
            } else if (v.kind === 'pattern') { if (typeof v.name !== 'string' || !v.name || v.name.length > 128) throw Error('Invalid pattern'); }
            else throw Error('Invalid paint kind');
        }
        one(p.fill); one(p.stroke); if (!range(p.stroke.width,0,1000)) throw Error('Invalid stroke width');
        if (p.mask && (!range(p.mask.feather,0,1000) || !range(p.mask.density,0,100))) throw Error('Invalid mask');
        if (!prepared.raw.vector && (!same(p.stroke, prepared.before.stroke) || !p.fill.enabled || p.fill.kind !== prepared.before.fill.kind)) throw Error('Ordinary fill type must remain unchanged');
    }
    function range(v, lo, hi) { return typeof v === 'number' && isFinite(v) && v >= lo && v <= hi; }
    function rgbDescriptor(v) { var d = new ActionDescriptor(); d.putDouble(s('red'),v[0]); d.putDouble(s('grain'),v[1]); d.putDouble(s('blue'),v[2]); return d; }
    var baseline, originalFill, originalFillType, originalStroke, originalPath, originalPixel, originalOrder, originalParent, originalMask, expectedRaw, applied, latest, lastSeq=0, updates=0, redraws=0;
    function build(value, previous, previousType) {
        var typeName;
        if(value.kind==='solid')typeName='solidColorLayer';else if(value.kind==='gradient')typeName='gradientLayer';else typeName='patternLayer';
        var type = s(typeName);
        var d = value.kind!=='solid' && type === previousType ? clone(previous) : new ActionDescriptor();
        if (value.kind === 'solid') d.putObject(c('Clr '),s('RGBColor'),rgbDescriptor(value.rgb));
        else if (value.kind === 'pattern') {
            var existing = previousType === type && previous.getObjectValue(s('pattern')).getString(c('Nm  ')) === value.name;
            var allowed = existing, i; for(i=0;i<prepared.before.patterns.length;i++) if(prepared.before.patterns[i]===value.name) allowed=true;
            if (!allowed) throw Error('Pattern catalog changed');
            if (!existing) { var pattern = new ActionDescriptor(); pattern.putString(c('Nm  '), value.name); d.putObject(s('pattern'),s('pattern'),pattern); }
        } else {
            if (type !== previousType) { d.putEnumerated(c('Type'),s('gradientType'),s('linear')); d.putUnitDouble(c('Angl'),c('#Ang'),0); d.putUnitDouble(c('Scl '),c('#Prc'),100); }
            var g = d.hasKey(s('gradient')) ? clone(d.getObjectValue(s('gradient'))) : new ActionDescriptor();
            if (!g.hasKey(c('Nm  '))) g.putString(c('Nm  '),'Menu gradient');
            g.putEnumerated(s('gradientForm'),s('gradientForm'),s('customStops')); g.putInteger(s('interfaceIconFrameDimmed'),4096);
            var old = g.hasKey(s('colors')) ? g.getList(s('colors')) : null, colors = new ActionList(), stop, midpoint;
            for (var n=0;n<value.stops.length;n++) { stop=new ActionDescriptor(); midpoint=old && n<old.count ? old.getObjectValue(n).getInteger(s('midpoint')) : 50; stop.putObject(c('Clr '),s('RGBColor'),rgbDescriptor(value.stops[n].rgb)); stop.putEnumerated(c('Type'),s('colorStopType'),s('userStop')); stop.putInteger(s('location'),value.stops[n].location); stop.putInteger(s('midpoint'),midpoint); colors.putObject(s('colorStop'),stop); }
            g.putList(s('colors'),colors);
            if (!g.hasKey(s('transparency'))) { var transparency=new ActionList(); for(var k=0;k<2;k++){stop=new ActionDescriptor();stop.putUnitDouble(c('Opct'),c('#Prc'),100);stop.putInteger(s('location'),k*4096);stop.putInteger(s('midpoint'),50);transparency.putObject(s('transferSpec'),stop);}g.putList(s('transparency'),transparency); }
            d.putObject(s('gradient'),s('gradientClassEvent'),g);
        }
        return {type:type, descriptor:d};
    }
    function defaultStroke() {
        var d=new ActionDescriptor();d.putInteger(s('strokeStyleVersion'),2);d.putBoolean(s('strokeEnabled'),false);d.putBoolean(s('fillEnabled'),true);d.putUnitDouble(s('strokeStyleLineWidth'),c('#Pxl'),1);var fill=new ActionDescriptor();fill.putObject(c('Clr '),s('RGBColor'),rgbDescriptor([0,0,0]));d.putObject(s('strokeStyleContent'),s('solidColorLayer'),fill);return d;
    }
    function verifyPaint(d, wanted) {
        var list=d.getList(s('adjustment')), fill=paint(list.getObjectValue(0),list.getObjectType(0));
        var stroke=d.hasKey(s('AGMStrokeStyleInfo'))?d.getObjectValue(s('AGMStrokeStyleInfo')):defaultStroke();
        if (!samePaint(fill,wanted.fill)) throw Error('Fill readback mismatch');
        if(prepared.raw.vector){var actual=paint(stroke.getObjectValue(s('strokeStyleContent')),stroke.getObjectType(s('strokeStyleContent')));if(!samePaint(actual,wanted.stroke) || stroke.getBoolean(s('strokeEnabled'))!==wanted.stroke.enabled || stroke.getBoolean(s('fillEnabled'))!==wanted.fill.enabled)throw Error('Stroke readback mismatch');var width=stroke.getUnitDoubleValue(s('strokeStyleLineWidth'));if(stroke.getUnitDoubleType(s('strokeStyleLineWidth'))===c('#Pnt'))width*=doc.resolution/72;if(Math.abs(width-wanted.stroke.width)>.01)throw Error('Stroke width mismatch');}
        if(wanted.mask && !maskClose(mask(d),wanted.mask))throw Error('Mask readback mismatch');
    }
    function setMaskProperty(key, unitID, value) { stage='write-'+key;target();var d=new ActionDescriptor(),r=new ActionReference(),v=new ActionDescriptor();r.putIdentifier(c('Lyr '),anchor.id);d.putReference(c('null'),r);v.putUnitDouble(s(key),c(unitID),value);d.putObject(c('T   '),c('Lyr '),v);executeAction(c('setd'),d,DialogModes.NO); }
    function apply(p) {
        stage='read-before-frame';validate(p);target();var d=layerDescriptor();
        if(!same(raw(d),expectedRaw) || prepared.raw.vector && !maskClose(mask(d),applied.mask || originalMask))throw Error('Style changed outside preview');
        var fillChanged=!same(p.fill,applied.fill),strokeChanged=!same(p.stroke,applied.stroke),frameChanged=false,to,newFill,newStroke,r,command;
        if(fillChanged || strokeChanged){
            to=prepared.raw.vector?new ActionDescriptor():null;
            if(fillChanged){newFill=build(p.fill,originalFill,originalFillType);if(to)to.putObject(s('fillContents'),newFill.type,newFill.descriptor);else to=newFill.descriptor;}
            if(prepared.raw.vector && (strokeChanged || p.fill.enabled!==applied.fill.enabled)){
                newStroke=clone(originalStroke);newStroke.putInteger(s('strokeStyleVersion'),2);newStroke.putBoolean(s('fillEnabled'),p.fill.enabled);
                if(strokeChanged){newStroke.putBoolean(s('strokeEnabled'),p.stroke.enabled);var oldContent=originalStroke.getObjectValue(s('strokeStyleContent'));var content=build(p.stroke,oldContent,originalStroke.getObjectType(s('strokeStyleContent')));newStroke.putObject(s('strokeStyleContent'),content.type,content.descriptor);newStroke.putUnitDouble(s('strokeStyleLineWidth'),c('#Pxl'),p.stroke.width);}
                to.putObject(s('strokeStyle'),s('strokeStyle'),newStroke);
            }
            stage='write-fill-stroke';target();command=new ActionDescriptor();r=new ActionReference();r.putEnumerated(s('contentLayer'),c('Ordn'),c('Trgt'));command.putReference(c('null'),r);command.putObject(c('T   '),prepared.raw.vector?s('shapeStyle'):newFill.type,to);executeAction(c('setd'),command,DialogModes.NO);changed=true;frameChanged=true;
        }
        if(p.mask){if(Math.abs(p.mask.feather-(applied.mask || originalMask).feather)>.00001){setMaskProperty('vectorMaskFeather','#Pxl',p.mask.feather);changed=true;frameChanged=true;}if(Math.abs(p.mask.density-(applied.mask || originalMask).density)>.00001){setMaskProperty('vectorMaskDensity','#Prc',p.mask.density);changed=true;frameChanged=true;}}
        stage='verify-frame';target();d=layerDescriptor();verifyPaint(d,p);expectedRaw=raw(d);applied=p;updates++;
        if(frameChanged){stage='redraw';app.refresh();redraws++;target();}
    }
    function readControl() {
        if(!mailbox.exists || mailbox.length>16384)return null;mailbox.encoding='UTF-8';if(!mailbox.open('r'))return null;var text;try{text=mailbox.read();}finally{mailbox.close();}return decode(text.replace(/^\uFEFF/,''));
    }
    function loop() {
        while(true){
            var value=null,now=new Date().getTime();try{value=readControl();}catch(_){}
            if(value && value.id===request.id && value.session===request.session && value.token===request.token && range(value.seq,1,2147483647) && Math.floor(value.seq)===value.seq && range(value.lease_until_ms,now,now+5000)){
                if(value.seq<lastSeq)throw Error('Preview sequence regressed');
                leaseUntil=value.lease_until_ms;
                if(value.phase==='cancel')return;
                if(value.phase!=='preview' && value.phase!=='commit')throw Error('Invalid preview phase');
                if(value.seq>lastSeq){apply(value.paint);latest=value.paint;lastSeq=value.seq;}
                if(value.phase==='commit'){commit=true;return;}
            }
            if(now>leaseUntil)return;$.sleep(20);
        }
    }
    var commit=false,leaseUntil=new Date().getTime()+4000;
    function invariants() { target();var d=layerDescriptor();if(parentID()!==originalParent || order().join(',')!==originalOrder.join(',') || pathStream()!==originalPath || !same(pixelMask(d),originalPixel))throw Error('Document structure or pixel mask changed');return d; }
    function rollback() { target();var current=layerDescriptor(),dirty=changed || !same(raw(current),raw(baseline)) || prepared.raw.vector && !maskClose(mask(current),originalMask);doc.activeHistoryState=originalHistory;if(dirty){app.refresh();redraws++;}var d=invariants();if(!same(raw(d),raw(baseline)) || prepared.raw.vector && !maskClose(mask(d),originalMask))throw Error('Legacy rollback readback mismatch'); }
    try {
        if(!app.documents.length)throw Error('Preview document closed');doc=app.activeDocument;anchor=doc.activeLayer;originalHistory=doc.activeHistoryState;
        target();validate(request.paint);if(prepared.before.revision!==request.paint.revision)throw Error('Prepared revision changed');stage='read-baseline';baseline=layerDescriptor();
        if(!same(raw(baseline),{fill:prepared.raw.fill,stroke:prepared.raw.stroke,vector:prepared.raw.vector}) || prepared.before.mask && !maskClose(mask(baseline),prepared.before.mask))throw Error('Prepared style changed before native dispatch');
        stage='clone-original';var list=baseline.getList(s('adjustment'));originalFill=clone(list.getObjectValue(0));originalFillType=list.getObjectType(0);originalStroke=baseline.hasKey(s('AGMStrokeStyleInfo'))?clone(baseline.getObjectValue(s('AGMStrokeStyleInfo'))):defaultStroke();
        stage='snapshot-invariants';originalPath=pathStream();originalPixel=pixelMask(baseline);originalOrder=order();originalParent=parentID();originalMask=prepared.raw.vector?mask(baseline):null;expectedRaw=raw(baseline);applied=prepared.before;latest=request.paint;
        if(originalParent!==prepared.parent_id || originalOrder.join(',')!==prepared.order.join(','))throw Error('Prepared parent or order changed');
        var key='__psMenuLegacy_'+request.id;if($.global[key])throw Error('Native request already active');$.global[key]=loop;historyStarted=true;
        stage='history-preview';try{doc.suspendHistory('Menu shape paint','$.global['+encode(key)+']()');}finally{delete $.global[key];}
        if(!commit){rollback();result={cancelled:true,rollback_verified:true,verified:true,paint:prepared.before};}
        else {var finalDescriptor=invariants();verifyPaint(finalDescriptor,latest);result={verified:true,count:changed?1:0,placement_moves:0,fill_kind:latest.fill.kind,stroke_kind:latest.stroke.kind,paint:latest};if(latest.mask)result.mask=latest.mask;}
        result.preview={updates:updates,redraws:redraws,last_seq:lastSeq,engine:'standalone-extendscript'};
        result={schema:1,id:request.id,session:request.session,operation:request.operation,token:request.token,phase:'completed',result:result};
    } catch(error) {
        var unknown=false;
        if(historyStarted){try{rollback();}catch(_){unknown=true;}}
        result={schema:1,id:request.id,session:request.session,operation:request.operation,token:request.token,phase:'failed',error:String(error),stage:stage,result_unknown:unknown};
    }
    var text=encode(result),temporary=new File(folder+'/legacy-result-'+request.id+'.tmp');
    if(receipt.exists)throw Error('Native receipt already exists; never overwrite');
    temporary.encoding='UTF-8';if(!temporary.open('w'))throw Error('Cannot save native receipt');try{temporary.write(text);}finally{temporary.close();}
    if(!temporary.rename(receipt.name))throw Error('Cannot publish native receipt');
    return text;
})();
