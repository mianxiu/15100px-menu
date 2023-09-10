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
    jsx = """"""
    return jsx
