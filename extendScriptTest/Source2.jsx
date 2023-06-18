var doc = activeDocument
var curLay = doc.activeLayer
var curLayIndex = curLay.itemIndex
var p = curLay.parent
var it = p.itemIndex
var n = p.name

$.writeln(
  '---SELECT------',
  curLay.itemIndex,
  ' layername: ',
  curLay.name,
  ' parentname: ',
  n,
)
var o = []

/**
 * 图层类的构造函数，传入一个图层ID
 * @param id
 * @constructor
 */
function Layer(id) {
  this.id = id
}

// ------- 类方法 -------
/**
 * 获取当前选中的图层
 * @return {Layer[]}
 */
Layer.getSelectedLayers = function () {
  // 创建一个ActionReference
  var selectedLayersReference = new ActionReference()
  // 给这个AR设置我们需要从AD中获取的属性值
  selectedLayersReference.putProperty(
    charIDToTypeID('Prpr'),
    stringIDToTypeID('targetLayersIDs'),
  )
  // 目标对象是当前选中的文档
  selectedLayersReference.putEnumerated(
    charIDToTypeID('Dcmn'),
    charIDToTypeID('Ordn'),
    charIDToTypeID('Trgt'),
  )
  var desc = executeActionGet(selectedLayersReference) // 拿到一个ActionDescriptor
  var layers = []
  if (desc.hasKey(stringIDToTypeID('targetLayersIDs'))) {
    // 拿到的是一个ID列表，我们遍历它把每个id拿出来，然后实例化Layer对象
    var list = desc.getList(stringIDToTypeID('targetLayersIDs'))
    for (var i = 0; i < list.count; i++) {
      var ar = list.getReference(i)
      var layerId = ar.getIdentifier()
      layers.push(new Layer(layerId))
    }
  }
  return layers
}

/**
 * 高效遍历图层
 * @param callback
 */
/*
Layer.loopLayers = function (callback) {
    var ref = new ActionReference();
        // 当前文档的图层数量属性key
        ref.putProperty(charIDToTypeID("Prpr"), charIDToTypeID('NmbL'));
        ref.putEnumerated( charIDToTypeID('Dcmn'), charIDToTypeID('Ordn'), charIDToTypeID('Trgt') );
    var desc = executeActionGet(ref);    
    var layerCount = desc.getInteger(charIDToTypeID('NmbL'));
    // 索引起始值，会受是否有背景图层影响，需要做一下处理
    var i = curLay.itemIndex;
    try {
        activeDocument.backgroundLayer;
    } catch(e) {
        i = curLay.itemIndex;
    }
    // 开始逐级遍历图层index，根据index来获取到图层实例
    for (i; i<layerCount+1; i++) {
        var ref = new ActionReference();
            ref.putIndex( charIDToTypeID( 'Lyr ' ), i );
        var desc = executeActionGet(ref);
        var id = desc.getInteger(stringIDToTypeID( 'layerID' ));
        var layer = new Layer(id);
        // 将遍历拿到的图层实例传递给回调函数，回调函数就可以根据自己的需要对图层进行操作了
        callback && callback(layer);
    }
}
*/
Layer.loopLayersBegin = function (callback) {
  var ref = new ActionReference()
  // 当前文档的图层数量属性key
  ref.putProperty(charIDToTypeID('Prpr'), charIDToTypeID('NmbL'))
  ref.putEnumerated(
    charIDToTypeID('Dcmn'),
    charIDToTypeID('Ordn'),
    charIDToTypeID('Trgt'),
  )
  var desc = executeActionGet(ref)
  var layerCount = desc.getInteger(charIDToTypeID('NmbL'))


  var i = curLayIndex
  var j = curLayIndex-1
  // 索引起始值，会受是否有背景图层影响，需要做一下处理
  var firstLayerIndex = 0
  try {
    activeDocument.backgroundLayer
  } catch (e) {
    firstLayerIndex = 1
  }

  function LyrId(index) {
    var ref = new ActionReference()
    ref.putIndex(charIDToTypeID('Lyr '), index)
    var desc = executeActionGet(ref)
    var id = desc.getInteger(stringIDToTypeID('layerID'))
    return id
  }

  // 开始逐级遍历图层index，根据index来获取到图层实例
  // up find
  /*
  for (i; i < layerCount + 1; i++) {
    var forward = i + 1
    if (forward <= layerCount + 1) {
      var layer = new Layer(LyrId(i))
      var layerName = layer.name()
      var layerKind = layer.kind()
      if (layerName == n || layerKind == 7) {
        // find group
        //  $.writeln(layer.name()," | forward num: ",forward," |  i num: ",i," | kind: ",layerKind," | index: ",layer.index())
        break
      } else {
        $.writeln(
          layer.name(),
          ' | forward num: ',
          forward,
          ' |  i num: ',
          i,
          ' | kind: ',
          layerKind,
          ' | index: ',
          layer.index(),
          ' | ▲',
        )
      }

      //$.writeln("++++++",layer.index()," ",layer.name(),"=",forward,"+",i)
      // 将遍历拿到的图层实例传递给回调函数，回调函数就可以根据自己的需要对图层进行操作了
      callback && callback(layer)
    }
  }
*/
  
  // down
  for (j; j > 0; j--) {
    // 无Background  after = j ， 有 after = j-1
    var after = j - 1 + firstLayerIndex
    if (after >=  firstLayerIndex) {
      var layer = new Layer(LyrId(after))
      var layerName = layer.name()
      var layerKind = layer.kind()

      if (layerName == n || layerKind == 7) {
        // find group
        /*
        $.writeln(
          layer.name(),
          ' | forward num: ',
          after,
          ' |  i num: ',
          i,
          ' | kind: ',
          layerKind,
          ' | index: ',
          layer.index(),
        )
        */
        break
      } else {
        $.writeln(
          layer.name(),
          ' | after num: ',
          after,
          ' |  j num: ',
          j,
          ' | kind: ',
          layerKind,
          ' | index: ',
          layer.index(),
          ' | ▼',
        )
      }

      //$.writeln("++++++",layer.index()," ",layer.name(),"=",forward,"+",i)
      // 将遍历拿到的图层实例传递给回调函数，回调函数就可以根据自己的需要对图层进行操作了
      callback && callback(layer)
    }
  }
}

// ------- 实例方法 -------
/**
 * 获取当前实例图层的名称
 * @return {string}
 */
Layer.prototype.name = function () {
  var layerReference = new ActionReference()
  layerReference.putProperty(charIDToTypeID('Prpr'), charIDToTypeID('Nm  '))
  layerReference.putIdentifier(charIDToTypeID('Lyr '), this.id)
  var descriptor = executeActionGet(layerReference)
  return descriptor.getString(charIDToTypeID('Nm  '))
}

/**
 * 获取当前实例图层的层级
 * @return {number}
 */
Layer.prototype.index = function () {
  var layerReference = new ActionReference()
  layerReference.putProperty(charIDToTypeID('Prpr'), charIDToTypeID('ItmI'))
  layerReference.putIdentifier(charIDToTypeID('Lyr '), this.id)
  var descriptor = executeActionGet(layerReference)
  return descriptor.getInteger(charIDToTypeID('ItmI'))
}

/**
 * 获取当前实例图层的类型
 * @return {number}
 */
Layer.prototype.kind = function () {
  var layerReference = new ActionReference()
  layerReference.putProperty(
    charIDToTypeID('Prpr'),
    stringIDToTypeID('layerKind'),
  )
  layerReference.putIdentifier(charIDToTypeID('Lyr '), this.id)
  var descriptor = executeActionGet(layerReference)
  return descriptor.getInteger(stringIDToTypeID('layerKind'))
}

// 使用方法
Layer.loopLayersBegin(function (layer) {
  //$.writeln(layer.index()," ",layer.name())
})
