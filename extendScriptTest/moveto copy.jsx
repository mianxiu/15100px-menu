//
//
// 执行后记得focus ps

//alert("Selected Layer: " + activeDocument.activeLayer + " - ItemIndex: " + activeDocument.activeLayer.itemIndex)
var isDontMove = false;
var isBegin = false
var isEnd = false;

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
  var isMoveToTop = false;

  var TopLayerIndex = 0;
  var BottomLayerIndex = 0;

  var SHOWDIALOG = false;

  var doc = activeDocument;
  var curLay = doc.activeLayer;
  var curLayIndex = curLay.itemIndex;
  var curLayKind = curLay.typename;

  // var curLayParent = curLay.parent;
  // var parentIndex = curLayParent.itemIndex;
  // var curLayParentName = curLayParent.name;

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
    isBegin = true
    
    if (isMoveToTop == true) {
      for (i; i < layerCount + 1; i++) {
        // 不包含选中图层 forward = i  + firstLayerIndex， 包含选中图层 forward =  i - 1  + firstLayerIndex
        var forward = i + firstLayerIndex;
        try {
          var layer = new Layer(LyrId(forward));
        } catch (e) {
          // 向上遍历
          TopLayerIndex = forward;
          break;
        }

        var layerKind = layer.kind();

        if (layerKind == 13 || layerKind == 7) {
          TopLayerIndex = forward - firstLayerIndex;
          //$.writeln(TopLayerIndex);
          break;
        }
      }
    } else {
      for (j; j > 0; j--) {
        // down
        // 无Background  after = j ， 有 after = j-1
        var after = j - 1 + firstLayerIndex;
        var layer = new Layer(LyrId(after));
        var layerKind = layer.kind();

        if (layerKind == 13 || layerKind == 7) {
          BottomLayerIndex = after + 1;
          break;
        }
      }
    }
  };

  Layer.loopLayerFromGroup = function () {
    var groupCount = 1;
    if (isMoveToTop == true) {
      // todo
      var i = curLayIndex;
      for (i; i < layerCount + 1; i++) {
        // 不包含选中图层 forward = i  + firstLayerIndex， 包含选中图层 forward =  i - 1  + firstLayerIndex
        var forward = i + firstLayerIndex;
        try {
          var layer = new Layer(LyrId(forward));
        } catch (e) {
          // 向上遍历
          TopLayerIndex = forward;
          break;
        }

        var layerKind = layer.kind();
        //$.writeln("层名字： ", layer.name());
        if (layerKind == 13) {
          groupCount += 1;
          isBegin = true
          //$.writeln("层开始： ", groupCount);
        }
        if (layerKind == 7) {
          groupCount -= 1;
          $.writeln("闭合：", groupCount);
          TopLayerIndex = forward;
        }
        if (groupCount == 0 && layerKind == 7) {
          var lastLayer = new Layer(LyrId(forward - 1));
          $.writeln("结尾：", groupCount, " ", curLayIndex, i, forward - 1);
          if (curLayIndex == forward) {
            isDontMove = true;
          }
          TopLayerIndex = forward;
          isEnd = true;
          break;
        }
      }
    } else {
      var j = curLayIndex - 1;
      TopLayerIndex = curLayIndex - 2 + firstLayerIndex;
      for (j; j > 0; j--) {
        // 无Background  after = j ， 有 after = j-1
        var after = j + firstLayerIndex - 1;
        var layer = new Layer(LyrId(after));
        var layerKind = layer.kind();
        $.writeln("层名字： ", layer.name());
        
        if (layerKind == 7) {
          groupCount += 1;
          $.writeln("层开始： ", groupCount);
          isBegin = true
        }
        if (layerKind == 13) {
          groupCount -= 1;
          BottomLayerIndex = after + 1;
          
          $.writeln("闭合index： ", after);
          if (groupCount == -1 && layerKind == 13) {
            BottomLayerIndex = after + 1;
            isEnd = true;
            break;
          }
        }
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



  if (curLayKind !== "LayerSet") {
    Layer.loopLayerBinarySearch();
  } else {
    Layer.loopLayerFromGroup();
  }

   if(isBegin == false){
        isDontMove = true 
 }
  $.writeln(TopLayerIndex, "--", BottomLayerIndex, "-", isDontMove," ",isBegin);
  if (isDontMove == false) {
    if (isMoveToTop == true) move(TopLayerIndex);
    else move(BottomLayerIndex);
  }

  // move group
}

app.activeDocument.suspendHistory("moveTo", "jsx()");
