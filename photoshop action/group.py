# select all layer in group
# apply l clear filter for all layer in group
# copy target layer filter and apply

LAYER_INDEX = r"""
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

"""

LAYER_KIND = r"""
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

"""

LAYERID = r"""
function LyrId(index) {
  var ref = new ActionReference();
  ref.putIndex(charIDToTypeID("Lyr "), index);
  var desc = executeActionGet(ref);
  var id = desc.getInteger(stringIDToTypeID("layerID"));
  return id;
}
"""

SELECT_LAYER_BY_INDEX = r"""
function actionManagerSelectLayerByIndex(itemIndex, makeVisible) {
  var d1 = new ActionDescriptor();
  var r1 = new ActionReference();
  r1.putIndex(stringIDToTypeID("layer"), itemIndex);
  d1.putReference(stringIDToTypeID("null"), r1);
  d1.putBoolean(stringIDToTypeID("MkVs"), makeVisible);
  executeAction(stringIDToTypeID("select"), d1, DialogModes.NO);
}
"""

SELECT_LAYER_BY_INDEX_CONTINUOUS = r"""
function selectLayerByIndexContinuous(index, makeVisible) {
  var desc1 = new ActionDescriptor();
  var ref1 = new ActionReference();
  ref1.putIndex(charIDToTypeID("Lyr "), index);
  desc1.putReference(charIDToTypeID("null"), ref1);
  desc1.putEnumerated(stringIDToTypeID("selectionModifier"), stringIDToTypeID("selectionModifierType"), stringIDToTypeID("addToSelectionContinuous"));
  desc1.putBoolean(charIDToTypeID("MkVs"), makeVisible);
  executeAction(charIDToTypeID("slct"), desc1, DialogModes.NO);
}
"""


def select_all_layer_in_group():
    jsx = r"""
 var TopLayerIndex = 0;
var BottomLayerIndex = 0;

var SHOWDIALOG = false;

var doc = activeDocument;
var curLay = doc.activeLayer;
var curLayIndex = curLay.itemIndex;
var curLayKind = curLay.typename;
var firstLayerIndex = 0;
try {
  activeDocument.backgroundLayer;
} catch (e) {
  firstLayerIndex = 1;
  BottomLayerIndex = 1;
}

Layer.loopLayerBinarySearch = function (callback) {
  var i = curLayIndex;
  var j = curLayIndex - 1;
  // 索引起始值，会受是否有背景图层影响，需要做一下处理

  // 开始逐级遍历图层index，根据index来获取到图层实例
  // up find
  layerCount = 30000;
  for (i; i < layerCount + 1; i++) {
    // 不包含选中图层 forward = i  + firstLayerIndex， 包含选中图层 forward =  i - 1  + firstLayerIndex
    var forward = i + firstLayerIndex - 1;

    try {
      var layer = new Layer(LyrId(forward));
    } catch (e) {
      TopLayerIndex = forward - 1;
      break;
    }
    var layerKind = layer.kind();
    if (layerKind == 13 || layerKind == 7) {
      TopLayerIndex = forward - 1;
      break;
    }
  }

  for (j; j > 0; j--) {
    // 无Background  after = j ， 有 after = j-1
    var after = j - 1 + firstLayerIndex;
    var layer = new Layer(LyrId(after));
    var layerKind = layer.kind();

    if (layerKind == 13 || layerKind == 7) {
      BottomLayerIndex = after + 1;
      break;
    }
  }
};

Layer.loopLayerFromGroup = function () {
  var j = curLayIndex - 1;
  TopLayerIndex = curLayIndex - 2 + firstLayerIndex;

  for (j; j > 0; j--) {
    // 无Background  after = j ， 有 after = j-1
    var after = j - 1 + firstLayerIndex;
    var layer = new Layer(LyrId(after));
    var layerKind = layer.kind();

    if (layerKind == 13 || layerKind == 7) {
      //$.writeln(after + firstLayerIndex)
      if (curLayIndex !== after + 2) {
        BottomLayerIndex = after + 1;
      }
      break;
    }
  }
};

"""


# app.doJavaScript(jsx)return
