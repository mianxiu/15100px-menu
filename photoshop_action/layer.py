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
