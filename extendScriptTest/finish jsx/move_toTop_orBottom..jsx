function moveToFront(){
    
    var desc1 = new ActionDescriptor();
var ref1 = new ActionReference();
ref1.putEnumerated( charIDToTypeID( "Lyr " ), charIDToTypeID( "Ordn" ), charIDToTypeID( "Trgt" ) );
desc1.putReference( charIDToTypeID( "null" ), ref1 );
var ref2 = new ActionReference();
ref2.putEnumerated( charIDToTypeID( "Lyr " ), charIDToTypeID( "Ordn" ), charIDToTypeID( "Back" ) );
desc1.putReference( charIDToTypeID( "T   " ), ref2 );
executeAction( charIDToTypeID( "move" ), desc1, DialogModes.NO );
    
    }


function moveToBack(){
    
    var desc1 = new ActionDescriptor();
var ref1 = new ActionReference();
ref1.putEnumerated( charIDToTypeID( "Lyr " ), charIDToTypeID( "Ordn" ), charIDToTypeID( "Trgt" ) );
desc1.putReference( charIDToTypeID( "null" ), ref1 );
var ref2 = new ActionReference();
ref2.putEnumerated( charIDToTypeID( "Lyr " ), charIDToTypeID( "Ordn" ), charIDToTypeID( "Frnt" ) );
desc1.putReference( charIDToTypeID( "T   " ), ref2 );
executeAction( charIDToTypeID( "move" ), desc1, DialogModes.NO );
    
    }


var isTop = true;/*%Bool%*/

if(isTop == true){
    
moveToFront()
    }else{
moveToBack ()        
        
        }