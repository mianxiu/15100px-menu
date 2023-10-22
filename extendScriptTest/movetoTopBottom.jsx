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

function jsx() {
  var layerCount = 30000;
  var isMoveToTop = true;

  var TopLayerIndex = 0;
  var BottomLayerIndex = 0;

  var SHOWDIALOG = false;

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

  var firstLayerIndex = 0;
  try {
    activeDocument.backgroundLayer;
    isHasBackground = true;
  } catch (e) {
    firstLayerIndex = 1;
    BottomLayerIndex = 1;
  }

  var ref = new ActionReference();
  // 当前文档的图层数量属性key
  ref.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("NmbL"));
  ref.putEnumerated(charIDToTypeID("Dcmn"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
  var desc = executeActionGet(ref);
  var layerCount = desc.getInteger(charIDToTypeID("NmbL"));

  //$.writeln("---SELECT------ curLayerIndex: ", curLay.itemIndex, " layername: ", curLay.name, " parentname: ", curLayParentName, " parentIndex: ", parentIndex, " typename: ", curLayKind,"i=",i,"j=",j);
  if (parentIndex != undefined) {
    TopLayerIndex = parentIndex - 1;
  } else {
    TopLayerIndex = layerCount;
  }

  //
  if (curLayIndex == TopLayerIndex) {
    isDontMove = true;
  }

  Layer.loopLayerFromGroup = function () {
    $.writeln("tu:", layerCount);
    //layerCount = 30000;
    layerCount = layerCount + 1;

    var groupCount = 0;
    var i = curLayIndex;
    var j = curLayIndex - 1;
    // 索引起始值，会受是否有背景图层影响，需要做一下处理

    // 开始逐级遍历图层index，根据index来获取到图层实例
    // up find
    function findGroup(layerKind) {
      if (layerKind == 7) {
        groupCount += 1;
        $.writeln("组开始 ", groupCount, "+", layerKind);
      }

      if (layerKind == 13) {
        groupCount -= 1;
        $.writeln("组结束 ", groupCount, "-", layerKind);
      }
    }

    for (j; j > 0; j--) {
      var layer = new Layer(LyrId(j));
      var layerKind = layer.kind();
      var layerName = layer.name();
      $.writeln("向下 ", "j=", j, " ", groupCount, "-", layerKind, "-", layerName);

      if (groupCount == 0 && layerKind == 13) {
        BottomLayerIndex = j + 1;
        if (curLayIndex == BottomLayerIndex) {
          isDontMove = true;
        }
        $.writeln("最底 ", "j=", j, " ", groupCount, "-", layerKind, "-", layerName,"~~",curLayIndex ,"!!",BottomLayerIndex);
        break;
      } else {
        findGroup(layerKind);
      }
    }
  };
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

  function runInGroup() {
    // if (isBegin == false) {
    //   isDontMove = true;
    // }
    $.writeln(TopLayerIndex, "--", BottomLayerIndex, "-", isDontMove, " ", isBegin);
    if (isDontMove == false) {
      Layer.loopLayerFromGroup();
      if (isMoveToTop == true) {
        app.activeDocument.suspendHistory("moveToTop (in group)", "move(TopLayerIndex)");
        //move(TopLayerIndex);
      } else {
        app.activeDocument.suspendHistory("moveToBottom(in group)", "move(BottomLayerIndex)");
      }
    }
  }

  function runOutGroup() {
    if (isDontMove == false) {
      Layer.loopLayerFromGroup();

      if (isHasBackground == true) {
        BottomLayerIndex = 1;
      } else {
        BottomLayerIndex = 0;
      }
      if (isMoveToTop == true) {
        app.activeDocument.suspendHistory("moveToTop (out group)", "move(TopLayerIndex)");
      } else {
        app.activeDocument.suspendHistory("moveToBottom(out group)", "move(BottomLayerIndex)");
      }
    }
  }

  if (parentIndex != undefined) {
    runInGroup();
    //app.activeDocument.suspendHistory("moveTo", "runjsx()");
  } else {
    runOutGroup();
  }
  // move group
}

jsx();
