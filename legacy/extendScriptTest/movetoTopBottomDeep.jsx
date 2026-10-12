//
//
// 执行后记得focus ps

//alert("Selected Layer: " + activeDocument.activeLayer + " - ItemIndex: " + activeDocument.activeLayer.itemIndex)
var isDontMove = false;
var isBegin = false;
var isEnd = false;
var isHasBackground = false;

function move(layerIndex) {
  var desc1 = new ActionDescriptor();
  var ref1 = new ActionReference();
  ref1.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
  desc1.putReference(charIDToTypeID("null"), ref1);
  var ref2 = new ActionReference();
  ref2.putIndex(charIDToTypeID("Lyr "), layerIndex);
  desc1.putReference(charIDToTypeID("T   "), ref2);
  desc1.putBoolean(charIDToTypeID("Adjs"), false);
  try {
    executeAction(charIDToTypeID("move"), desc1, DialogModes.NO);
  } catch (e) {}
}


  var layerCount = 30000;
  var isMoveToTop = false;

  var TopLayerIndex = 0;
  var BottomLayerIndex = 0;


  var doc = activeDocument;
  var curLay = doc.activeLayer;
  var curLayIndex = curLay.itemIndex;
  var curLayKind = curLay.typename;

  var curLayParent = curLay.parent;
  var parentIndex = curLayParent.itemIndex;
  var curLayParentName = curLayParent.name;

  //$.writeln("---SELECT------ curLayerIndex: ", curLay.itemIndex, " layername: ", curLay.name, " parentname: ", curLayParentName, " parentIndex: ", parentIndex," typename: ",curLayKind);

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

  // ------- 实例方法 -------
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


//
  var firstLayerIndex = 0;
  function getBackgroundInfo() {
  try {
    activeDocument.backgroundLayer;
    isHasBackground = true;
  } catch (e) {
    firstLayerIndex = 1;
    BottomLayerIndex = 1;
  }

  var ref = new ActionReference();
  
  // 当前文档的图层数量属性key
  // 图层数量不包含背景
  ref.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("NmbL"));
  ref.putEnumerated(charIDToTypeID("Dcmn"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
  var desc = executeActionGet(ref);
  layerCount = desc.getInteger(charIDToTypeID("NmbL"));
  if(isHasBackground == true){
  layerCount += firstLayerIndex
  }
}





// loopGround

function loopLayer(){
    getBackgroundInfo()
    for(var i= firstLayerIndex;i<=layerCount;i++){
        var layer = new Layer(LyrId(i));
        $.writeln(layer.name())
        }
   
}

loopLayer()
