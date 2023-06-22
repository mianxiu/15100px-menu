// 选中组内的所有图层
// 选中组间的所有图层
// 选择同级的

function actionManagerSelectLayerByIndex(itemIndex, makeVisible) {
  var d1 = new ActionDescriptor();
  var r1 = new ActionReference();
  r1.putIndex(stringIDToTypeID("layer"), itemIndex);
  d1.putReference(stringIDToTypeID("null"), r1);
  d1.putBoolean(stringIDToTypeID("MkVs"), makeVisible);
  executeAction(stringIDToTypeID("select"), d1, DialogModes.NO);
}

//alert("Selected Layer: " + activeDocument.activeLayer + " - ItemIndex: " + activeDocument.activeLayer.itemIndex)

function selectLayerByIndexContinuous(index, makeVisible) {
  var desc1 = new ActionDescriptor();
  var ref1 = new ActionReference();
  ref1.putIndex(charIDToTypeID("Lyr "), index);
  //ref1.putName( charIDToTypeID( "Lyr " ), "Layer 17" );
  desc1.putReference(charIDToTypeID("null"), ref1);
  desc1.putEnumerated(stringIDToTypeID("selectionModifier"), stringIDToTypeID("selectionModifierType"), stringIDToTypeID("addToSelectionContinuous"));
  desc1.putBoolean(charIDToTypeID("MkVs"), makeVisible);
  executeAction(charIDToTypeID("slct"), desc1, DialogModes.NO);
}

var SHOWDIALOG = false;

var doc = activeDocument;
var curLay = doc.activeLayer;
var curLayIndex = curLay.itemIndex;
var curLayKind = curLay.typename;
var curLayParent = curLay.parent;
var parentIndex = curLayParent.itemIndex;
var curLayParentName = curLayParent.name;

$.writeln("---SELECT------ cur index", curLay.itemIndex, " layername: ", curLay.name, " parentname: ", curLayParentName, " parentIndex: ", parentIndex, " typename: ", curLayKind);

/**
 * 图层类的构造函数，传入一个图层ID
 * @param id
 * @constructor
 */
function Layer(id) {
  this.id = id;
}

// ------- 类方法 -------
/**
 * 获取当前选中的图层
 * @return {Layer[]}
 */
Layer.getSelectedLayers = function () {
  // 创建一个ActionReference
  var selectedLayersReference = new ActionReference();
  // 给这个AR设置我们需要从AD中获取的属性值
  selectedLayersReference.putProperty(charIDToTypeID("Prpr"), stringIDToTypeID("targetLayersIDs"));
  // 目标对象是当前选中的文档
  selectedLayersReference.putEnumerated(charIDToTypeID("Dcmn"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
  var desc = executeActionGet(selectedLayersReference); // 拿到一个ActionDescriptor
  var layers = [];
  if (desc.hasKey(stringIDToTypeID("targetLayersIDs"))) {
    // 拿到的是一个ID列表，我们遍历它把每个id拿出来，然后实例化Layer对象
    var list = desc.getList(stringIDToTypeID("targetLayersIDs"));
    for (var i = 0; i < list.count; i++) {
      var ar = list.getReference(i);
      var layerId = ar.getIdentifier();
      layers.push(new Layer(layerId));
    }
  }
  return layers;
};

/**
 * 高效遍历图层
 * @param callback
 */

function LyrId(index) {
  var ref = new ActionReference();
  ref.putIndex(charIDToTypeID("Lyr "), index);
  var desc = executeActionGet(ref);
  var id = desc.getInteger(stringIDToTypeID("layerID"));
  return id;
}

var TopLayerIndex = 0;
var BottomLayerIndex = 0;

var backgroundIndex = 0;
try {
  activeDocument.backgroundLayer;
} catch (e) {
  // if no background
  backgroundIndex = 1;
  BottomLayerIndex = 1;
}

Layer.loopLayerBinarySearch = function (callback) {
  var i = curLayIndex;
  var j = curLayIndex;
  // 索引起始值，会受是否有背景图层影响，需要做一下处理

  // 开始逐级遍历图层index，根据index来获取到图层实例
  // up find
  layerCount = 30000;
  for (i; i < layerCount; i++) {
    // 不包含选中图层 forward = i  + firstLayerIndex， 包含选中图层 forward =  i - 1  + firstLayerIndex
    var after = i + 1;

    var layer = new Layer(LyrId(after));

    var layerName = layer.name();
    var layerKind = layer.kind();

    $.writeln("after: " + after + " kind: " + layerKind + " name: " + layerName);

    if (layerKind == 13 || layerKind == 7) {
      TopLayerIndex = i;
      break;
    }
  }

  for (j; j > backgroundIndex; j--) {
    var forward = j - 1;
    var layer = new Layer(LyrId(forward));

    var layerName = layer.name();
    var layerKind = layer.kind();

    $.writeln("forward: " + forward + " j: " + j + " kind: " + layerKind + " name: " + layerName);

    if (layerKind == 13 || layerKind == 7) {
      BottomLayerIndex = j;
      break;
    }
  }
};

// ------- 实例方法 -------
/**
 * 获取当前实例图层的名称
 * @return {string}
 */
Layer.prototype.name = function () {
  var layerReference = new ActionReference();
  layerReference.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("Nm  "));
  layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
  var descriptor = executeActionGet(layerReference);
  return descriptor.getString(charIDToTypeID("Nm  "));
};

/**
 * 获取当前实例图层的层级
 * @return {number}
 */
Layer.prototype.index = function () {
  var layerReference = new ActionReference();
  layerReference.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("ItmI"));
  layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
  var descriptor = executeActionGet(layerReference);
  return descriptor.getInteger(charIDToTypeID("ItmI"));
};

/**
 * 获取当前实例图层的类型
 * @return {number}
 */
Layer.prototype.kind = function () {
  var layerReference = new ActionReference();
  layerReference.putProperty(charIDToTypeID("Prpr"), stringIDToTypeID("layerKind"));
  layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
  var descriptor = executeActionGet(layerReference);
  return descriptor.getInteger(stringIDToTypeID("layerKind"));
};

// 使用方法
/*
Layer.loopLayersBegin(function (layer) {
  //$.writeln(layer.index(), ' ', layer.name())
});
*/
Layer.loopLayerBinarySearch();
/*
if (parentIndex == undefined) {
  Layer.loopLayerBinarySearch();
} else {
  Layer.loopForwardDown();
}
    
    
    */
$.writeln("TopLayerIndex: " + TopLayerIndex + " BottomLayerIndex: " + BottomLayerIndex);
actionManagerSelectLayerByIndex(BottomLayerIndex, true);
selectLayerByIndexContinuous(TopLayerIndex, true);
//actionManagerSelectLayerByIndex(TopLayerIndex, true);
