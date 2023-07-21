//  
// 
// 执行后记得focus ps

//alert("Selected Layer: " + activeDocument.activeLayer + " - ItemIndex: " + activeDocument.activeLayer.itemIndex)

function move(layerIndex) {
  var desc1 = new ActionDescriptor();
  var ref1 = new ActionReference();
  ref1.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
  desc1.putReference(charIDToTypeID("null"), ref1);
  var ref2 = new ActionReference();
  ref2.putIndex(charIDToTypeID("Lyr "), layerIndex);
  desc1.putReference(charIDToTypeID("T   "), ref2);
  desc1.putBoolean(charIDToTypeID("Adjs"), false);
  executeAction(charIDToTypeID("move"), desc1, DialogModes.NO);
}

function jsx() {
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
    if (isMoveToTop == true) {
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
          TopLayerIndex = forward;
          $.writeln(TopLayerIndex);
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
         if (isMoveToTop == true) {}
         else{
    var groupCount = 1
    var j = curLayIndex - 1;
    TopLayerIndex = curLayIndex - 2 + firstLayerIndex;
    for (j; j > 0; j--) {
      // 无Background  after = j ， 有 after = j-1
      var after = j - 1 + firstLayerIndex;
      var layer = new Layer(LyrId(after));
      var layerKind = layer.kind();
      
      if(layerKind == 7 && groupCount > 0){
          groupCount += 1
          $.writeln("子层： ", groupCount)
       }
      if(layerKind == 13 && groupCount > 0){
            groupCount -= 1
            //$.writeln(groupCount)
          }
      if(groupCount <=0){
          
           $.writeln("~~层： ", groupCount,"  layerKind :",layerKind," name: ",layer.name())
           }
     // if (layerKind == 13 || layerKind == 7) {
     //   if (curLayIndex !== after + 2) {
    //      BottomLayerIndex = after + 1;
    //    }
   //     break;
   //   }
    }
  };
}
  // ------- 实例方法 -------
  Layer.prototype.name = function() {
    var layerReference = new ActionReference();
        layerReference.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("Nm  "));
        layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
    var descriptor = executeActionGet(layerReference);
    return descriptor.getString(charIDToTypeID("Nm  "));
}


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
    if (isMoveToTop == true) {
      move(TopLayerIndex);
    } else {
      move(BottomLayerIndex);
    }
  } else {
        Layer.loopLayerFromGroup ()
    // move group
  }
}
app.activeDocument.suspendHistory("moveTo", "jsx()");
