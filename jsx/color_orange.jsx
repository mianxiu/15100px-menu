var desc1 = new ActionDescriptor();
        var ref1 = new ActionReference();
        ref1.putEnumerated( charIDToTypeID( "Lyr " ), charIDToTypeID( "Ordn" ), charIDToTypeID( "Trgt" ) );
        desc1.putReference( charIDToTypeID( "null" ), ref1 );
        var desc2 = new ActionDescriptor();
        desc2.putEnumerated( charIDToTypeID( "Clr " ), charIDToTypeID( "Clr " ), charIDToTypeID( "Orng" ) );
        desc1.putObject( charIDToTypeID( "T   " ), charIDToTypeID( "Lyr " ), desc2 );
        executeAction( charIDToTypeID( "setd" ), desc1, DialogModes.NO );
