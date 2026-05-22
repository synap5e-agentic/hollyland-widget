import QtQuick
import Quickshell
import qs.Commons
import qs.Services.UI
import "qml" as HollylandUi

Item {
  id: root

  property var pluginApi: null
  property ShellScreen screen
  property string widgetId: ""
  property string section: ""
  property int sectionWidgetIndex: -1
  property int sectionWidgetsCount: 0

  readonly property string screenName: screen ? screen.name : ""
  readonly property string barPosition: Settings.getBarPositionForScreen(screenName)
  readonly property bool isVertical: barPosition === "left" || barPosition === "right"
  readonly property real capsuleHeight: Style.getCapsuleHeightForScreen(screenName)
  readonly property real barFontSize: Style.getBarFontSizeForScreen(screenName)

  readonly property var mainInstance: pluginApi?.mainInstance

  implicitWidth: widget.implicitWidth
  implicitHeight: widget.implicitHeight

  HollylandUi.HollylandBar {
    id: widget
    anchors.fill: parent
    labelText: root.mainInstance ? root.mainInstance.barPrimaryText() : "HL"
    secondaryText: root.mainInstance ? root.mainInstance.barSecondaryText() : ""
    accent: root.mainInstance ? root.mainInstance.statusColor() : Color.mOnSurfaceVariant
    txItems: root.mainInstance ? root.mainInstance.barTransmitterItems() : []
    isVertical: root.isVertical
    capsuleHeight: root.capsuleHeight
    barFontSize: root.barFontSize
  }

  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.LeftButton | Qt.MiddleButton

    onClicked: function(mouse) {
      if (mouse.button === Qt.LeftButton && root.pluginApi)
        root.pluginApi.togglePanel(root.screen, root);
      if (mouse.button === Qt.MiddleButton && root.mainInstance)
        root.mainInstance.refreshState();
    }

    onEntered: {
      if (root.mainInstance)
        TooltipService.show(root, root.mainInstance.tooltipText(), BarService.getTooltipDirection());
    }

    onExited: {
      TooltipService.hide();
    }
  }
}
