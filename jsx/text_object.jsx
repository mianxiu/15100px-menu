/* One PDF text object transaction. Called only while UXP reserves this request. */
(function(){
    var request=__PS_MENU_TEXT_OBJECT_REQUEST__,s=stringIDToTypeID,c=charIDToTypeID;
    var prepared=request.prepared,source=request.source,doc=null,anchor=null,work=null,history=null,changed=false,result,colorType,colorValue,documentsBefore=null,dialogs=null,identityConflict=false;
    var folder=new Folder(request.folder),pdf=new File(folder+'/text-object-'+request.id+'.pdf'),receipt=new File(folder+'/legacy-result-'+request.id+'.json');
    __PS_MENU_TEXT_HASH_HELPER__
    function encode(v){
        if(v===null)return 'null';
        if(typeof v==='string')return '"'+v.replace(/["\\\x00-\x1f]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4);})+'"';
        if(typeof v==='number'){if(!isFinite(v))throw Error('Invalid source number');return String(v);}
        if(typeof v==='boolean')return String(v);
        var a=[],i,keys=[];if(v instanceof Array){for(i=0;i<v.length;i++)a.push(encode(v[i]));return '['+a.join(',')+']';}
        for(i in v)if(v.hasOwnProperty(i)&&typeof v[i]!=='undefined')keys.push(i);
        keys.sort();for(i=0;i<keys.length;i++)a.push(encode(keys[i])+':'+encode(v[keys[i]]));return '{'+a.join(',')+'}';
    }
    function name(id){return typeIDToStringID(id)||typeIDToCharID(id);}
    function documents(){var ids=[];for(var i=0;i<app.documents.length;i++)ids.push(app.documents[i].id);ids.sort(function(a,b){return a-b;});return ids;}
    function contains(ids,id){for(var i=0;i<ids.length;i++)if(ids[i]===id)return true;return false;}
    function unit(id){if(id===c('#Pxl'))return 'pixelsUnit';if(id===c('#Pnt'))return 'pointsUnit';if(id===c('#Prc'))return 'percentUnit';if(id===c('#Ang'))return 'angleUnit';return name(id);}
    function object(d){var o={},i,k;for(i=0;i<d.count;i++){k=d.getKey(i);o[name(k)]=item(d,k);}return o;}
    function item(d,k){
        var t=d.getType(k),o,i;
        if(t===DescValueType.OBJECTTYPE){o=object(d.getObjectValue(k));o._obj=name(d.getObjectType(k));return o;}
        if(t===DescValueType.LISTTYPE){o=[];var a=d.getList(k);for(i=0;i<a.count;i++)o.push(item(a,i));return o;}
        if(t===DescValueType.ENUMERATEDTYPE)return {_enum:name(d.getEnumerationType(k)),_value:name(d.getEnumerationValue(k))};
        if(t===DescValueType.UNITDOUBLE)return {_unit:unit(d.getUnitDoubleType(k)),_value:d.getUnitDoubleValue(k)};
        if(t===DescValueType.DOUBLETYPE)return d.getDouble(k);if(t===DescValueType.INTEGERTYPE)return d.getInteger(k);
        if(t===DescValueType.BOOLEANTYPE)return d.getBoolean(k);if(t===DescValueType.STRINGTYPE)return d.getString(k);
        throw Error('Unsupported text descriptor');
    }
    function property(key){var r=new ActionReference();r.putProperty(s('property'),s(key));r.putIdentifier(s('layer'),app.activeDocument.activeLayer.id);return executeActionGet(r);}
    function rawText(){return object(property('textKey')).textKey;}
    function metadata(){var d=property('XMPMetadataAsUTF8');return d.hasKey(s('XMPMetadataAsUTF8'))?d.getString(s('XMPMetadataAsUTF8')):'';}
    function setMetadata(xml){var r=new ActionReference(),a=new ActionDescriptor(),v=new ActionDescriptor();r.putProperty(s('property'),s('XMPMetadataAsUTF8'));r.putIdentifier(s('layer'),app.activeDocument.activeLayer.id);a.putReference(s('null'),r);v.putString(s('XMPMetadataAsUTF8'),xml);a.putObject(s('to'),s('layer'),v);executeAction(s('set'),a,DialogModes.NO);}
    function renderHash(suffix){var file=new File(folder+'/text-object-'+suffix+'-'+request.id+'.pdf');if(file.exists)throw Error('Render evidence already exists');var a=new ActionDescriptor();a.putPath(c('null'),file);executeAction(s('placedLayerExportContents'),a,DialogModes.NO);if(file.length>16777216)throw Error('Vector source exceeds16MiB');file.encoding='BINARY';if(!file.open('r'))throw Error('Cannot read vector source');try{var bytes=file.read();if(bytes.slice(0,5)!=='%PDF-')throw Error('Vector source format mismatch');return sha256(bytes);}finally{file.close();}}
    function finalMetadata(){
        var digest=renderHash('render');if(!ExternalObject.AdobeXMPScript)ExternalObject.AdobeXMPScript=new ExternalObject('lib:AdobeXMPScript');
        XMPMeta.registerNamespace('https://15100px.menu/ns/text-object/1.0/','pxText');var meta=new XMPMeta(request.xmp);meta.setProperty('https://15100px.menu/ns/text-object/1.0/','render',digest);request.xmp=meta.serialize();
        var value={schema:1,id:request.id,session:request.session,operation:request.operation,token:request.token,xmp:request.xmp},file=new File(folder+'/text-object-final-'+request.id+'.json');if(file.exists)throw Error('Final source evidence already exists');file.encoding='UTF-8';if(!file.open('w'))throw Error('Cannot persist final source evidence');try{file.write(encode(value));}finally{file.close();}
    }
    function target(start){
        if(!app.documents.length||app.activeDocument.id!==request.target.document_id||app.activeDocument.activeLayer.id!==request.target.active_layer_id)throw Error('Text object target changed');
        if(request.target.layer_ids.length!==1)throw Error('Select one text object');
        if(start&&new Date().getTime()>request.expires_at_ms)throw Error('Text object request expired before execution');
    }
    function put(d,key,v,list){
        var k=list?null:s(key),t=typeof v;
        function call(method,args){if(!list)args.unshift(k);d[method].apply(d,args);}
        if(t==='string')call('putString',[v]);else if(t==='boolean')call('putBoolean',[v]);
        else if(t==='number')call(v===Math.floor(v)?'putInteger':'putDouble',[v]);
        else if(v instanceof Array){var a=new ActionList();for(var i=0;i<v.length;i++)put(a,null,v[i],true);call('putList',[a]);}
        else if(v&&v._unit)call('putUnitDouble',[s(v._unit),v._value]);
        else if(v&&v._enum)call('putEnumerated',[s(v._enum),s(v._value)]);
        else if(v&&v._obj)call('putObject',[s(v._obj),descriptor(v)]);else throw Error('Unsupported source value');
    }
    function descriptor(value){var d=new ActionDescriptor();for(var key in value)if(value.hasOwnProperty(key)&&key!=='_obj')put(d,key,value[key],false);return d;}
    function applyText(raw){
        var to={_obj:'textLayer'},keys=['textKey','textStyleRange','paragraphStyleRange','antiAlias','orientation','textGridding','textShape','textClickPoint','transform','warp','kerningRange'];
        for(var i=0;i<keys.length;i++)if(raw.hasOwnProperty(keys[i]))to[keys[i]]=raw[keys[i]];
        var a=new ActionDescriptor(),r=new ActionReference();r.putEnumerated(s('textLayer'),s('ordinal'),s('targetEnum'));a.putReference(s('null'),r);a.putObject(s('to'),s('textLayer'),descriptor(to));executeAction(s('set'),a,DialogModes.NO);
    }
    function signature(style){var o={},key;if(style.baseParentStyle)o=signature(style.baseParentStyle);for(key in style)if(style.hasOwnProperty(key)&&key!=='_obj'&&key!=='baseParentStyle'&&key!=='styleSheetHasParent'&&key!=='fontAvailable'&&key!=='fontName'&&key!=='fontStyleName'&&key.indexOf('implied')!==0)o[key]=style[key];return o;}
    function checkText(actual,wanted){
        if(actual.textKey!==wanted.textKey)throw Error('Text source content readback mismatch');
        var keys=['textStyleRange','paragraphStyleRange'];
        for(var k=0;k<keys.length;k++){
            var field=k===0?'textStyle':'paragraphStyle',a=actual[keys[k]],b=wanted[keys[k]],ai=0,bi=0;
            function effective(rows,index){var o=signature(rows[0][field].baseParentStyle||{}),v=signature(rows[index][field]);for(var p in v)if(v.hasOwnProperty(p))o[p]=v[p];var b=o.baselineShift;if(b===undefined||b===0)o.baselineShift=0;else if(b&&b._unit==='pointsUnit')o.baselineShift=b._value*source.canvas.resolution/72;else if(b&&b._unit==='pixelsUnit')o.baselineShift=b._value;return encode(o);}
            var left=[],right=[],j;for(j=0;j<a.length;j++)left.push(effective(a,j));for(j=0;j<b.length;j++)right.push(effective(b,j));
            for(var offset=0;offset<wanted.textKey.length;offset++){while(ai<a.length-1&&offset>=a[ai].to)ai++;while(bi<b.length-1&&offset>=b[bi].to)bi++;if(left[ai]!==right[bi])throw Error('Text source style readback mismatch');}
        }
    }
    function checkSourceFonts(raw){var runs=raw.textStyleRange;for(var i=0;i<runs.length;i++){var font=signature(runs[i].textStyle).fontPostScriptName;if(typeof font!=='string'||!font)throw Error('Source font identity missing');try{app.fonts.getByName(font);}catch(e){throw Error('Source font unavailable: '+font);}}}
    function layout(value){var shape=value.textShape&&value.textShape[0];return {orientation:value.orientation,transform:value.transform,warp:value.warp&&value.warp.warpStyle&&value.warp.warpStyle._value==='warpNone'?value.warp.warpStyle:value.warp,shape:{'char':shape['char'],orientation:shape.orientation,transform:shape.transform,bounds:shape['char']._value==='box'?shape.bounds:null}};}
    function near(a,b){if(typeof a==='number'&&typeof b==='number')return Math.abs(a-b)<.00001;if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;var k,keys=0;for(k in a)if(a.hasOwnProperty(k)){keys++;if(!b.hasOwnProperty(k)||!near(a[k],b[k]))return false;}for(k in b)if(b.hasOwnProperty(k))keys--;return keys===0;}
    function replace(){
        target();changed=true;
        if(prepared.kind==='smart-object'){
            executeAction(s('placedLayerMakeCopy'),new ActionDescriptor(),DialogModes.NO);
            var a=new ActionDescriptor();a.putPath(s('null'),pdf);a.putInteger(s('crop'),2);executeAction(s('placedLayerReplaceContents'),a,DialogModes.NO);
        }else{
            var a=new ActionDescriptor();a.putPath(c('null'),pdf);a.putEnumerated(c('FTcs'),c('QCSt'),c('Qcsa'));a.putInteger(s('crop'),2);executeAction(c('Plc '),a,DialogModes.NO);
        }
        var created=doc.activeLayer;if(created.id===anchor.id||created.kind!==LayerKind.SMARTOBJECT)throw Error('Vector object creation failed');
        var vector=object(property('smartObject')).smartObject;if(vector.placed._value!=='vectorData'||vector.linked)throw Error('Embedded vector source readback mismatch');
        var more=object(property('smartObjectMore')).smartObjectMore,frame=more.transform;
        var expected=prepared.kind==='smart-object'?prepared.transform:[0,0,source.canvas.width,0,source.canvas.width,source.canvas.height,0,source.canvas.height];
        if(prepared.kind==='text'&&Math.abs(frame[2]-frame[0]-source.canvas.width)<.01&&Math.abs(frame[5]-frame[1]-source.canvas.height)<.01&&Math.abs(frame[3]-frame[1])<.01&&Math.abs(frame[6]-frame[0])<.01){created.translate(UnitValue(-frame[0],'px'),UnitValue(-frame[1],'px'));frame=object(property('smartObjectMore')).smartObjectMore.transform;}
        if(!expected||frame.length!==8)throw Error('Text object frame missing');for(var i=0;i<8;i++)if(Math.abs(frame[i]-expected[i])>.01)throw Error('Text object placement readback mismatch: '+encode({crop:more.crop,frame:frame,expected:expected,size:more.size}));
        if(created.parent.typename!==anchor.parent.typename||created.parent.id!==anchor.parent.id)throw Error('Vector object parent changed');
        finalMetadata();setMetadata(request.xmp);if(metadata()!==request.xmp)throw Error('Text object metadata readback mismatch');
        var label=new ActionDescriptor(),value=new ActionDescriptor(),ref=new ActionReference();ref.putIdentifier(s('layer'),created.id);label.putReference(s('null'),ref);value.putEnumerated(s('color'),colorType,colorValue);label.putObject(s('to'),s('layer'),value);executeAction(s('set'),label,DialogModes.NO);
        if(property('color').getEnumerationValue(s('color'))!==colorValue)throw Error('Text object color label readback mismatch');
        created.name=anchor.name;created.visible=anchor.visible;anchor.remove();
        if(doc.activeLayer.id!==created.id)throw Error('Text object selection readback mismatch');
        result={verified:true,count:1,layer_id:created.id,source_sha256:prepared.source_sha256,engine:'native-pdf-vector'};
    }
    try{
        if(!/^[0-9a-f]{32}$/.test(request.id))throw Error('Invalid text object identity');
        if(receipt.exists||pdf.exists||new File(folder+'/legacy-result-'+request.id+'.tmp').exists||new File(folder+'/text-object-before-'+request.id+'.pdf').exists||new File(folder+'/text-object-render-'+request.id+'.pdf').exists||new File(folder+'/text-object-final-'+request.id+'.json').exists){identityConflict=true;throw Error('Text object identity already used; preserve original unknown');}
        if(request.command!=='text.object'||!source||source.schema!==1||!prepared)throw Error('Invalid text object command');
        if(sha256('abc')!=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')throw Error('SHA256 self-check failed');
        target(true);doc=app.activeDocument;anchor=doc.activeLayer;history=doc.activeHistoryState;documentsBefore=documents();
        dialogs=app.displayDialogs;app.displayDialogs=DialogModes.NO;
        var label=property('color');colorType=label.getEnumerationType(s('color'));colorValue=label.getEnumerationValue(s('color'));
        if(metadata()!==prepared.before_xmp)throw Error('Text object metadata changed');
        if(prepared.kind==='text'&&encode(rawText())!==encode(prepared.before_text))throw Error('Text source changed');
        if(prepared.kind==='smart-object'&&renderHash('before')!==prepared.before_render)throw Error('Vector content changed outside this tool; original object was not updated');
        if(prepared.kind==='text'){
            var check=new ActionReference();check.putIdentifier(s('layer'),anchor.id);var state=executeActionGet(check);
            if(anchor.opacity!==100||anchor.fillOpacity!==100||anchor.blendMode!==BlendMode.NORMAL||anchor.grouped||state.hasKey(s('layerEffects'))||state.hasKey(s('hasUserMask'))&&state.getBoolean(s('hasUserMask'))||state.hasKey(s('hasVectorMask'))&&state.getBoolean(s('hasVectorMask')))throw Error('Text object creation currently requires normal text without masks, effects or clipping');
        }
        checkSourceFonts(source.layer.text);
        var raw=source.layer.text,shape=raw.textShape&&raw.textShape[0],matrix=raw.transform||{xx:1,yy:1,xy:0,yx:0};
        if(raw.kerningRange&&raw.kerningRange.length)throw Error('Manual kerning is not supported by the content editor');
        if(!shape||raw.textShape.length!==1||(shape['char']._value!=='paint'&&shape['char']._value!=='box')||raw.orientation._value!=='horizontal'||raw.warp&&raw.warp.warpStyle._value!=='warpNone'||(shape.columnCount||1)!==1||(shape.rowCount||1)!==1||Math.abs(matrix.xx-1)>.00001||Math.abs(matrix.yy-1)>.00001||Math.abs(matrix.xy)>.00001||Math.abs(matrix.yx)>.00001)throw Error('Vector source currently requires horizontal, unwarped, single-column text');
        var canvas=source.canvas;if(canvas.mode!=='RGB'||canvas.depth!==8)throw Error('Vector text currently requires RGB8 source');
        work=app.documents.add(UnitValue(canvas.width,'px'),UnitValue(canvas.height,'px'),canvas.resolution,'Text object '+request.id,NewDocumentMode.RGB,DocumentFill.TRANSPARENT,1,BitsPerChannelType.EIGHT,canvas.profile);
        if(contains(documentsBefore,work.id))throw Error('Source workspace identity invalid');
        if(prepared.kind==='text'){app.activeDocument=doc;var copy=anchor.duplicate(work,ElementPlacement.PLACEATBEGINNING);app.activeDocument=work;work.activeLayer=copy;}
        else{var copy=work.artLayers.add();copy.kind=LayerKind.TEXT;}
        copy.visible=true;copy.textItem.kind=shape['char']._value==='box'?TextType.PARAGRAPHTEXT:TextType.POINTTEXT;applyText(source.layer.text);
        var click=source.layer.text.textClickPoint;
        if(!click||!click.horizontal||!click.vertical||click.horizontal._unit!=='percentUnit'||click.vertical._unit!=='percentUnit')throw Error('Unsupported native text anchor units');
        copy.textItem.position=[UnitValue(click.horizontal._value*canvas.width/100,'px'),UnitValue(click.vertical._value*canvas.height/100,'px')];
        var actualText=rawText();checkText(actualText,source.layer.text);if(!near(layout(actualText),layout(source.layer.text)))throw Error('Text source layout readback mismatch');
        if(Math.abs(actualText.textClickPoint.horizontal._value-click.horizontal._value)>.00001||Math.abs(actualText.textClickPoint.vertical._value-click.vertical._value)>.00001)throw Error('Text anchor readback mismatch');
        var options=new PDFSaveOptions();options.preserveEditing=false;options.embedColorProfile=true;work.saveAs(pdf,options,true,Extension.LOWERCASE);
        work.close(SaveOptions.DONOTSAVECHANGES);work=null;app.activeDocument=doc;target();if(encode(documents())!==encode(documentsBefore))throw Error('Source document cleanup mismatch');
        if(doc.activeHistoryState.id!==history.id||metadata()!==prepared.before_xmp||prepared.kind==='text'&&encode(rawText())!==encode(prepared.before_text))throw Error('Original changed during source generation');
        var key='__psMenuTextObject_'+request.id;if($.global[key])throw Error('Text object already running');$.global[key]=replace;
        try{doc.suspendHistory('Vector text object','$.global['+encode(key)+']()');}finally{delete $.global[key];}
        if(encode(documents())!==encode(documentsBefore))throw Error('Final document inventory mismatch');
        result={schema:1,id:request.id,session:request.session,operation:request.operation,token:request.token,phase:'completed',result:result};
    }catch(error){
        var unknown=identityConflict,restore='';
        try{if(work){if(contains(documentsBefore,work.id))throw Error('Source workspace ownership unavailable');app.activeDocument=work;work.close(SaveOptions.DONOTSAVECHANGES);work=null;}if(doc){app.activeDocument=doc;if(changed){doc.activeHistoryState=history;doc.activeLayer=anchor;if(metadata()!==prepared.before_xmp)throw Error('Metadata restore mismatch');if(prepared.kind==='text'&&encode(rawText())!==encode(prepared.before_text))throw Error('Text restore mismatch');}if(encode(documents())!==encode(documentsBefore))throw Error('Source document cleanup unknown');}}catch(e){unknown=true;restore=String(e);}
        result={schema:1,id:request.id,session:request.session,operation:request.operation,token:request.token,phase:'failed',error:String(error),error_line:error.line,result_unknown:unknown,not_executed:!changed&&!unknown,rollback_error:restore};
    }
    try{if(dialogs!==null)app.displayDialogs=dialogs;}catch(error){result.phase='failed';result.result_unknown=true;result.error='Photoshop dialog state restore unknown: '+String(error);}
    var text=encode(result),temporary=new File(folder+'/legacy-result-'+request.id+'.tmp');
    if(receipt.exists)throw Error('Native receipt already exists');temporary.encoding='UTF-8';if(!temporary.open('w'))throw Error('Cannot persist native result');try{temporary.write(text);}finally{temporary.close();}if(!temporary.rename(receipt.name))throw Error('Cannot publish native result');return text;
})();
