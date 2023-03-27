
/*
This is a UI file (.ui.qml) that is intended to be edited in Qt Design Studio only.
It is supposed to be strictly declarative and only uses a subset of QML. If you edit
this file manually, you might introduce QML code that is not supported by Qt Design Studio.
Check out https://doc.qt.io/qtcreator/creator-quick-ui-forms.html for details on .ui.qml files.
*/
import QtQuick 6.2
import QtQuick.Controls 6.2



Rectangle {
    id: rectangle
    width: 500
    height: 500
    color: "#00ffffff"

    RoundButton {
        id: roundButton
        width: 209
        height: 36
        text: "+1234"
    }

    RoundButton {
        id: button
        text: "A Special Button"
        checkable: true

        background: Rectangle {
            implicitWidth: 100
            implicitHeight: 40
            color: button.pressed ? "#00cc00" : button.hovered ? "#00cc00" : button.activeFocus ? "#00cc00" : "#ffff00"
            border.color: "#26282a"
            border.width: 2
            radius: 20
            
        }

        HoverHandler {
        id: stylus
        acceptedDevices: PointerDevice.Stylus
        cursorShape: Qt.CrossCursor
        }

        Item {
            QtObject {
                id: attributes
                property string name
                property int size
                property variant attributes
            }

            Text {
                text: attributes.name
            }
        }
    }

    Text {
        id: label
        text: qsTr("S 2023-3-12")
        anchors.top: button.bottom
        anchors.topMargin: 45
        anchors.horizontalCenter: parent.horizontalCenter
        font.pixelSize: 16
        color:"#ffffff"
    }
    states: [
        State {
            name: "clicked"
            when: button.checked

            PropertyChanges {
                target: label
                text: qsTr("Button Checked")
            }
        }
    ]
}