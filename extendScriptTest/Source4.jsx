
/*
var desc1 = new ActionDescriptor();
var ref1 = new ActionReference();
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 20" );
desc1.putReference( charIDToTypeID( "null" ), ref1 );
desc1.putBoolean( charIDToTypeID( "MkVs" ), false );
var list1 = new ActionList();
list1.putInteger( 5801 );
desc1.putList( charIDToTypeID( "LyrI" ), list1 );
executeAction( charIDToTypeID( "slct" ), desc1, DialogModes.NO );
*/

/*
var desc1 = new ActionDescriptor();
var ref1 = new ActionReference();
ref1.putIndex( charIDToTypeID( "Lyr " ), 2);
//ref1.putName( charIDToTypeID( "Lyr " ), "Layer 17" );
desc1.putReference( charIDToTypeID( "null" ), ref1 );
desc1.putEnumerated( stringIDToTypeID( "selectionModifier" ), stringIDToTypeID( "selectionModifierType" ), stringIDToTypeID( "addToSelectionContinuous" ) );
desc1.putBoolean( charIDToTypeID( "MkVs" ), false );
executeAction( charIDToTypeID( "slct" ), desc1, DialogModes.NO );
*/
/*
var desc1 = new ActionDescriptor();
var ref1 = new ActionReference();
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 17 - 2" );
desc1.putReference( charIDToTypeID( "null" ), ref1 );
desc1.putEnumerated( stringIDToTypeID( "selectionModifier" ), stringIDToTypeID( "selectionModifierType" ), stringIDToTypeID( "addToSelection" ) );
desc1.putBoolean( charIDToTypeID( "MkVs" ), false );
var list1 = new ActionList();
list1.putInteger( 5788 );
list1.putInteger( 5799 );
list1.putInteger( 5800 );
desc1.putList( charIDToTypeID( "LyrI" ), list1 );
executeAction( charIDToTypeID( "slct" ), desc1, DialogModes.NO );
*/

var desc1 = new ActionDescriptor();
var ref1 = new ActionReference();
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 20" );
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 19" );
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 23" );
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 22" );
ref1.putName( charIDToTypeID( "Lyr " ), "3" );
ref1.putName( charIDToTypeID( "Lyr " ), "Layer 14" );
ref1.putName( charIDToTypeID( "Lyr " ), "9" );
ref1.putName( charIDToTypeID( "Lyr " ), "8" );
ref1.putName( charIDToTypeID( "Lyr " ), "7" );
desc1.putReference( charIDToTypeID( "null" ), ref1 );
desc1.putBoolean( charIDToTypeID( "MkVs" ), false );
executeAction( charIDToTypeID( "slct" ), desc1, DialogModes.NO );