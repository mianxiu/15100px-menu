import photoshop_action.baseStr as baseStr


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


def moveToIndex(layerIndex: str, isMoveToTop=True):
    if isMoveToTop is True:
        isTrue = "true"
    else:
        isTrue = "false"
    jsx = ""

    return jsx


def moveLayerToTopOrBottom(isMoveToTop: bool = True):
    if isMoveToTop is True:
        boolStr = "true"
    else:
        boolStr = "false"
    jsx = (
        r""""""
        + baseStr.init()
        + r"""
var isDontMove = false;
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
  executeAction(charIDToTypeID("move"), desc1, DialogModes.NO);
}

function jsx() {
  var layerCount = 30000;
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
          //$.writeln("层开始： ", groupCount);
        }
        if (layerKind == 7) {
          groupCount -= 1;
          //$.writeln("闭合：", groupCount);
          TopLayerIndex = forward;
        }
        if (groupCount == 0 && layerKind == 7) {
          var lastLayer = new Layer(LyrId(forward - 1));
          //$.writeln("结尾：", groupCount, " ",curLayIndex, i,forward-1);
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
        var after = j + firstLayerIndex - 1;
        var layer = new Layer(LyrId(after));
        var layerKind = layer.kind();
        if (layerKind == 7) {
          groupCount += 1;
        }
        if (layerKind == 13) {
          groupCount -= 1;
          BottomLayerIndex = after + 1;
        }
        if (groupCount == -1 && layerKind == 13) {
          var lastLayer = new Layer(LyrId(after + 1));
          if (groupCount == -1 && lastLayer.kind() == 13) {
            isDontMove = true;
          }
          BottomLayerIndex = after + 1;
          isEnd = true;
          break;
        }
      }
    }
  };


  if (curLayKind !== "LayerSet") {
    Layer.loopLayerBinarySearch();
    }else{
      Layer.loopLayerFromGroup();
    }
    
    if (isDontMove == false) {
      if (isMoveToTop == true) move(TopLayerIndex);
      else move(BottomLayerIndex);
    }
  
}
app.activeDocument.suspendHistory("moveTo", "jsx()");
    """
    )
    return jsx
