import os

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


def init():
    jsx = r"""""" + LAYER_INDEX + LAYERID + LAYER_KIND
    return jsx
