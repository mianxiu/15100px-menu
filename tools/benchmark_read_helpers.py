"""Fixed, transparent scratch fixtures; no downloads, account or user content."""
import json, math, statistics
ACTIONS=['adjustment.curves','layer.new','adjustment.curves','adjustment.hueSaturation',
         'adjustment.colorBalance','adjustment.blackWhite','layer.solid','layer.new','layer.group','layer.new']
MODES=['dom','get','multiget']
def summary(values):
    ordered=sorted(values)
    return {'n':len(values),'median_ms':round(statistics.median(values),2),
            'p95_ms':round(ordered[max(0,math.ceil(.95*len(values))-1)],2),
            'min_ms':round(min(values),2),'max_ms':round(max(values),2)}

TREE=r'''(function(){var out=[];function walk(ls,parent){for(var i=0;i<ls.length;i++){var l=ls[i];out.push([parent,l.id,l.name].join('\t'));if(l.typename==='LayerSet')walk(l.layers,l.id);}}walk(app.activeDocument.layers,0);return out.join('\n');})();'''
SEMANTIC=r'''(function(){function find(ls){for(var i=0;i<ls.length;i++){if(ls[i].name==='Anchor')return ls[i];if(ls[i].typename==='LayerSet'){var hit=find(ls[i].layers);if(hit)return hit;}}}var s=stringIDToTypeID,r=new ActionReference(),anchor=find(app.activeDocument.layers);r.putIdentifier(s('layer'),anchor.id);var d=executeActionGet(r),out=[];var keys=['layerKind','hasVectorMask','hasUserMask','adjustment','textKey','smartObject','layerEffects','userMaskDensity','vectorMaskDensity'];for(var i=0;i<keys.length;i++){var k=s(keys[i]);if(d.hasKey(k)){var a=new ActionDescriptor();var t=d.getType(k);if(t==DescValueType.OBJECTTYPE)a.putObject(k,d.getObjectType(k),d.getObjectValue(k));else if(t==DescValueType.LISTTYPE)a.putList(k,d.getList(k));else if(t==DescValueType.BOOLEANTYPE)a.putBoolean(k,d.getBoolean(k));else if(t==DescValueType.INTEGERTYPE)a.putInteger(k,d.getInteger(k));else if(t==DescValueType.DOUBLETYPE)a.putDouble(k,d.getDouble(k));else continue;out.push(keys[i]+':'+a.toStream());}}if(d.hasKey(s('hasVectorMask'))&&d.getBoolean(s('hasVectorMask'))){var path=new ActionReference();path.putProperty(s('property'),s('pathContents'));path.putEnumerated(s('path'),s('path'),s('vectorMask'));path.putIdentifier(s('layer'),anchor.id);out.push('vectorPath:'+executeActionGet(path).toStream());}return out.join('\n');})();'''
# ActionDescriptor streams contain NUL; returning them directly through COM
# truncates the string. Encode all bytes before independent readback.
SEMANTIC=SEMANTIC.replace('(function(){','(function(){function hex(v){var out="";for(var i=0;i<v.length;i++)out+=("00"+(v.charCodeAt(i)&255).toString(16)).slice(-2);return out;}')
SEMANTIC=SEMANTIC.replace('a.toStream()','hex(a.toStream())').replace('executeActionGet(path).toStream()','hex(executeActionGet(path).toStream())')

def native(action):
    if action=='layer.new':return "var s=stringIDToTypeID,r=new ActionReference();r.putClass(s('layer'));var d=new ActionDescriptor();d.putReference(s('null'),r);executeAction(s('make'),d,DialogModes.NO);"
    if action=='layer.group':return "var s=stringIDToTypeID,r=new ActionReference();r.putClass(s('layerSection'));var d=new ActionDescriptor();d.putReference(s('null'),r);r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));d.putReference(s('from'),r);executeAction(s('make'),d,DialogModes.NO);"
    # Reuse the independently validated fixed native builders, without executing
    # their verifier's main function.
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('native_creation_reference',Path(__file__).with_name('verify-created-layers.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.native(action)

def special(kind):
    if kind=='text':return 'var a=d.artLayers.add();a.kind=LayerKind.TEXT;a.textItem.contents="Shape count test";a.textItem.size=9;'
    if kind in ('smart','masked'):
        base='var a=d.artLayers.add();d.activeLayer=a;d.selection.selectAll();d.selection.fill(app.foregroundColor);d.selection.deselect();'
        if kind=='smart':return base+"executeAction(stringIDToTypeID('newPlacedLayer'),undefined,DialogModes.NO);"
        return base+"var s=stringIDToTypeID,z=new ActionDescriptor();z.putClass(s('new'),s('channel'));var r=new ActionReference();r.putEnumerated(s('channel'),s('channel'),s('mask'));z.putReference(s('at'),r);z.putEnumerated(s('using'),s('userMaskEnabled'),s('revealAll'));executeAction(s('make'),z,DialogModes.NO);"
    if kind in ('solid','curves'):return native('layer.solid' if kind=='solid' else 'adjustment.curves')
    if kind=='levels':return "var s=stringIDToTypeID,r=new ActionReference();r.putClass(s('adjustmentLayer'));var t=new ActionDescriptor();t.putEnumerated(s('presetKind'),s('presetKindType'),s('presetKindDefault'));var u=new ActionDescriptor();u.putObject(s('type'),s('levels'),t);var z=new ActionDescriptor();z.putReference(s('null'),r);z.putObject(s('using'),s('adjustmentLayer'),u);executeAction(s('make'),z,DialogModes.NO);"
    if kind=='shape':return native('layer.solid').replace("z.putObject(s('using'),s('contentLayer'),u);", "var q=new ActionDescriptor();q.putUnitDouble(s('top'),s('pixelsUnit'),8);q.putUnitDouble(s('left'),s('pixelsUnit'),8);q.putUnitDouble(s('bottom'),s('pixelsUnit'),48);q.putUnitDouble(s('right'),s('pixelsUnit'),40);u.putObject(s('shape'),s('rectangle'),q);z.putObject(s('using'),s('contentLayer'),u);")
    if kind=='gradient':return "var s=stringIDToTypeID,r=new ActionReference();r.putClass(s('contentLayer'));var t=new ActionDescriptor();t.putEnumerated(s('type'),s('gradientType'),s('linear'));t.putUnitDouble(s('angle'),s('angleUnit'),0);var gradient=new ActionDescriptor();gradient.putString(s('name'),'Benchmark Black White');gradient.putEnumerated(s('gradientForm'),s('gradientForm'),s('customStops'));gradient.putDouble(s('interfaceIconFrameDimmed'),4096);var colors=new ActionList();for(var i=0;i<2;i++){var stop=new ActionDescriptor(),rgb=new ActionDescriptor();rgb.putDouble(s('red'),255*i);rgb.putDouble(s('green'),255*i);rgb.putDouble(s('blue'),255*i);stop.putObject(s('color'),s('RGBColor'),rgb);stop.putEnumerated(s('type'),s('colorStopType'),s('userStop'));stop.putInteger(s('location'),4096*i);stop.putInteger(s('midpoint'),50);colors.putObject(s('colorStop'),stop);}gradient.putList(s('colors'),colors);var stops=new ActionList();for(var j=0;j<2;j++){var stop=new ActionDescriptor();stop.putUnitDouble(s('opacity'),s('percentUnit'),100);stop.putInteger(s('location'),4096*j);stop.putInteger(s('midpoint'),50);stops.putObject(s('transferSpec'),stop);}gradient.putList(s('transparency'),stops);t.putObject(s('gradient'),s('gradientClassEvent'),gradient);var u=new ActionDescriptor();u.putObject(s('type'),s('gradientLayer'),t);var z=new ActionDescriptor();z.putReference(s('null'),r);z.putObject(s('using'),s('contentLayer'),u);executeAction(s('make'),z,DialogModes.NO);"
    raise ValueError(kind)

def fixture(kind,count):
    # Initial measured fixtures resolved numeric 64 under this PS profile's
    # millimetre ruler units to 181x181 pixels. Fix those actual dimensions for
    # reproduction; never assume unqualified DOM numbers mean pixels.
    header='app.documents.add(UnitValue(181,"px"),UnitValue(181,"px"),72,"Read strategy benchmark scratch '+kind+str(count)+'",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);var d=app.activeDocument;'
    script='var lower=d.artLayers.add();lower.name="Lower";'
    script+=special('shape' if kind=='mixed' else kind)+'var anchor=d.activeLayer;anchor.name="Anchor";var upper=d.artLayers.add();upper.name="Upper";'
    if kind=='mixed':
        for item in ('solid','gradient','text','smart','curves','levels'):script+=special(item)
        script+='var templates=[];for(var k=0;k<d.layers.length;k++)templates.push(d.layers[k]);for(var i=d.layers.length;i<'+str(count)+';i++)templates[i%templates.length].duplicate();'
    else:script+='for(var i=d.layers.length;i<'+str(count)+';i++)anchor.duplicate();'
    script+='d.activeLayer=anchor;'
    return header+'d.suspendHistory("Read benchmark fixture",'+json.dumps(script)+');'
