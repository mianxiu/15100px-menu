# select all layer in group
# apply l clear filter for all layer in group
# copy target layer filter and apply
import time

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
/**
 * 图层类的构造函数，传入一个图层ID
 * @param id
 * @constructor
 */
function Layer(id) {
  this.id = id;
}

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
    i = time.ctime()
    jsx = (
        r""""""
        + LAYER_INDEX
        + LAYERID
        + LAYER_KIND
        + r"""

var selectMulitLayerDesc1 = new ActionDescriptor();
var selectMulitLayerRef1 = new ActionReference();


var TopLayerIndex = 0;
var BottomLayerIndex = 0;


var curLay =activeDocument .activeLayer;
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
      // 向上遍历
      TopLayerIndex = forward - 1;
      selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), TopLayerIndex);
      break;
    }

    var layerKind = layer.kind();

    if (layerKind == 13 || layerKind == 7) {
      TopLayerIndex = forward - 1;
      //$.writeln(new Layer(LyrId(forward-1)).name()," Top Layer")
      selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), TopLayerIndex);
      break;
    } else {
      selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), forward);
    }
  }

  // finish
  // down

  for (j; j > 0; j--) {
    // 无Background  after = j ， 有 after = j-1
    var after = j - 1 + firstLayerIndex;
    var layer = new Layer(LyrId(after));
    var layerKind = layer.kind();

    if (layerKind == 13 || layerKind == 7) {
      BottomLayerIndex = after + 1;

      selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), BottomLayerIndex);
      break;
    } else {
      selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), after);
    }
  }
};

Layer.loopLayerFromGroup = function () {
  var j = curLayIndex - 1;
  TopLayerIndex = curLayIndex - 2 + firstLayerIndex;
  selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), TopLayerIndex);
  for (j; j > 0; j--) {
    // 无Background  after = j ， 有 after = j-1
    var after = j - 1 + firstLayerIndex;
    var layer = new Layer(LyrId(after));
    var layerKind = layer.kind();

    if (layerKind == 13 || layerKind == 7) {
      //$.writeln(after + firstLayerIndex)
      if (curLayIndex !== after + 2) {
        BottomLayerIndex = after + 1;
        selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), BottomLayerIndex);
      }
      break;
    } else {
      selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), after);
    }

  }
};

// 使用方法
function jsx(){
if (curLayKind !== "LayerSet") {
  Layer.loopLayerBinarySearch();
  selectMulitLayerDesc1.putReference(charIDToTypeID("null"), selectMulitLayerRef1);
  selectMulitLayerDesc1.putBoolean(charIDToTypeID("MkVs"), false);
  executeAction(charIDToTypeID("slct"), selectMulitLayerDesc1, DialogModes.NO);

} else {
  Layer.loopLayerFromGroup();
  selectMulitLayerDesc1.putReference(charIDToTypeID("null"), selectMulitLayerRef1);
  selectMulitLayerDesc1.putBoolean(charIDToTypeID("MkVs"), false);
  executeAction(charIDToTypeID("slct"), selectMulitLayerDesc1, DialogModes.NO);
}
//$.writeln(curLayIndex)
return curLayIndex
}
app.activeDocument.suspendHistory ("Select All Layer """
        + str(i)
        + r"""", "jsx()")

"""
    )
    return jsx


# alert会阻塞线程
def alert():
    jsx = r"""
        var desc1 = new ActionDescriptor();
        var ref1 = new ActionReference();
        ref1.putEnumerated( charIDToTypeID( "Lyr " ), charIDToTypeID( "Ordn" ), charIDToTypeID( "Trgt" ) );
        desc1.putReference( charIDToTypeID( "null" ), ref1 );
        var desc2 = new ActionDescriptor();
        desc2.putEnumerated( charIDToTypeID( "Clr " ), charIDToTypeID( "Clr " ), charIDToTypeID( "Orng" ) );
        desc1.putObject( charIDToTypeID( "T   " ), charIDToTypeID( "Lyr " ), desc2 );
        executeAction( charIDToTypeID( "setd" ), desc1, DialogModes.NO );
  """
    return jsx
