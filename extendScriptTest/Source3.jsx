
// hold shift to select
/*
var desc1 = new ActionDescriptor();
var ref1 = new ActionReference();
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 19" );
desc1.putReference( charIDToTypeID( "null" ), ref1 );
desc1.putEnumerated( stringIDToTypeID( "selectionModifier" ), stringIDToTypeID( "selectionModifierType" ), stringIDToTypeID( "addToSelectionContinuous" ) );
desc1.putBoolean( charIDToTypeID( "MkVs" ), false );
executeAction( charIDToTypeID( "slct" ), desc1, DialogModes.NO );

*/

sTT = stringIDToTypeID;

function actionManagerSelectLayerByIndex(itemIndex, makeVisible){

    var d1 = new ActionDescriptor();
    var r1 = new ActionReference();

    r1.putIndex( sTT('layer'), itemIndex );
    d1.putReference( sTT('null'), r1 );
    d1.putBoolean( sTT('MkVs'), makeVisible );
    executeAction( sTT('select'), d1, DialogModes.NO );
    }

//alert("Selected Layer: " + activeDocument.activeLayer + " - ItemIndex: " + activeDocument.activeLayer.itemIndex)

actionManagerSelectLayerByIndex(activeDocument.activeLayer.itemIndex-5, true);

//alert("Selected Layer next: " + activeDocument.activeLayer + " - ItemIndex: " + activeDocument.activeLayer.itemIndex)