def s(layerIndex: str):
    jsx = (
        r"""
    function actionManagerSelectLayerByIndex(itemIndex, makeVisible) {
    var d1 = new ActionDescriptor();
    var r1 = new ActionReference();
    r1.putIndex(stringIDToTypeID("layer"), """
        + layerIndex
        + r""");
    d1.putReference(stringIDToTypeID("null"), r1);
    d1.putBoolean(stringIDToTypeID("MkVs"), makeVisible);
    executeAction(stringIDToTypeID("select"), d1, DialogModes.NO);
    }
    """
    )


def moveToIndex(layerIndex: str, isTop=True):
    if isTop is True:
        mLayerIndex = layerIndex
    else:
        mLayerIndex = layerIndex - 1
    jsx = (
        r"""
    var desc1 = new ActionDescriptor();
    var ref1 = new ActionReference();
    ref1.putEnumerated( charIDToTypeID( "Lyr " ), charIDToTypeID( "Ordn" ), charIDToTypeID( "Trgt" ) );
    desc1.putReference( charIDToTypeID( "null" ), ref1 );
    var ref2 = new ActionReference();
    ref2.putIndex( charIDToTypeID( "Lyr " ), """
        + mLayerIndex
        + r""" );
    desc1.putReference( charIDToTypeID( "T   " ), ref2 );
    desc1.putBoolean( charIDToTypeID( "Adjs" ), false );
    executeAction( charIDToTypeID( "move" ), desc1, DialogModes.NO );
    """
    )

    return jsx


def moveLayerToTopOrBottom(isTop: bool = True):
    if isTop is True:
        boolStr = "true"
    else:
        boolStr = "false"
    jsx = (
        r"""
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
  var isMoveToTop = """
        + boolStr
        + r"""

  var TopLayerIndex = 0;
  var BottomLayerIndex = 0;

  var SHOWDIALOG = false;

  var doc = activeDocument;
  var curLay = doc.activeLayer;
  var curLayIndex = curLay.itemIndex;
  var curLayKind = curLay.typename;


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
    var j = curLayIndex - 1;
    TopLayerIndex = curLayIndex - 2 + firstLayerIndex;
    selectMulitLayerRef1.putIndex(stringIDToTypeID("layer"), TopLayerIndex);
    for (j; j > 0; j--) {
      // 无Background  after = j ， 有 after = j-1
      var after = j - 1 + firstLayerIndex;
      var layer = new Layer(LyrId(after));
      var layerKind = layer.kind();

      if (layerKind == 13 || layerKind == 7) {
        if (curLayIndex !== after + 2) {
          BottomLayerIndex = after + 1;
        }
        break;
      }
    }
  };

  // ------- 实例方法 -------

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
    // move group
  }
}
app.activeDocument.suspendHistory("moveTo", "jsx()");  
    """
    )

    return jsx
