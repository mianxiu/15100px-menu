var doc = activeDocument;
var curLay = doc.activeLayer;
var p = curLay.parent
var it = p.itemIndex
var n = p.name
var allLay = doc.layers
var layer = allLay[1];

var o=[]

$.writeln (curLay.itemIndex+" "+n,layer)


for(var i=1;i<11;i++){
    
    

    $.writeln (allLay[i])
    }

/*
var desc1 = new ActionDescriptor();
var ref1 = new ActionReference();
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 3" );
desc1.putReference( charIDToTypeID( "null" ), ref1 );
desc1.putEnumerated( stringIDToTypeID( "selectionModifier" ), stringIDToTypeID( "selectionModifierType" ), stringIDToTypeID( "addToSelectionContinuous" ) );
desc1.putBoolean( charIDToTypeID( "MkVs" ), false );
var list1 = new ActionList();
list1.putInteger( 1 );
list1.putInteger( 11 );
desc1.putList( charIDToTypeID( "LyrI" ), list1 );
executeAction( charIDToTypeID( "slct" ), desc1, DialogModes.NO );
*/

