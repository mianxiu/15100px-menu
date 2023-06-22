// 选中组内的所有图层
// 选中组间的所有图层
// 起始选中组则选中子级的所有同级图层
// 起始选中图层就是区间内的
// 

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

var TopLayerIndex = 0;
var BottomLayerIndex = 0;

var SHOWDIALOG = false;

var doc = activeDocument;
var curLay = doc.activeLayer;
var curLayIndex = curLay.itemIndex;
var curLayKind = curLay.typename
var curLayParent = curLay.parent;
var parentIndex = curLayParent.itemIndex;
var curLayParentName = curLayParent.name;


$.writeln("---SELECT------", curLay.itemIndex, " layername: ", curLay.name, " parentname: ", curLayParentName, " parentIndex: ", parentIndex," typename: ",curLayKind);

/**
 * 图层类的构造函数，传入一个图层ID
 * @param id
 * @constructor
 */
function Layer(id) {
  this.id = id;
}

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

 var firstLayerIndex = 0;
 try {
    activeDocument.backgroundLayer;
  } catch (e) {
    firstLayerIndex = 1;
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
        break;
      }

      var layerKind = layer.kind();
      
      if (layerKind == 13 || layerKind == 7) {
          
        TopLayerIndex = forward - 1;
        //$.writeln(new Layer(LyrId(forward-1)).name()," Top Layer")
        break;
      }
  }

  // finish
  // down

  for (j; j > 0; j--) {
    // 无Background  after = j ， 有 after = j-1
    var after = j - 1 + firstLayerIndex;
    if (after >= firstLayerIndex) {
      var layer = new Layer(LyrId(after));
      var layerKind = layer.kind();

      if (layerKind == 13 || layerKind == 7) {
        BottomLayerIndex = after + 1;
        break;
      }
      // 将遍历拿到的图层实例传递给回调函数，回调函数就可以根据自己的需要对图层进行操作了
      //callback && callback(layer);
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

 Layer.loopLayerBinarySearch();

  
$.writeln("TopIndex: "+TopLayerIndex+" BottomIndex: "+BottomLayerIndex)
actionManagerSelectLayerByIndex(BottomLayerIndex, true);
selectLayerByIndexContinuous(TopLayerIndex, true);
//actionManagerSelectLayerByIndex(TopLayerIndex, true);
