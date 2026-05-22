import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Services.UI
import qs.Widgets
import "TxTheme.js" as TxTheme

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
  readonly property real dotSize: Math.max(8, Style.toOdd(capsuleHeight * 0.22))

  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property string labelText: mainInstance ? mainInstance.barPrimaryText() : "HL"
  readonly property string secondaryText: mainInstance ? mainInstance.barSecondaryText() : ""
  readonly property color accent: mainInstance ? mainInstance.statusColor() : Color.mOnSurfaceVariant
  readonly property var txItems: mainInstance ? mainInstance.barTransmitterItems() : []

  implicitWidth: isVertical ? capsuleHeight : capsule.implicitWidth
  implicitHeight: capsuleHeight

  Rectangle {
    id: capsule
    x: Style.pixelAlignCenter(parent.width, width)
    y: Style.pixelAlignCenter(parent.height, height)
    implicitWidth: mainRow.implicitWidth + Style.marginL * 2
    width: implicitWidth
    height: parent.height
    radius: Style.radiusL
    color: Style.capsuleColor
    border.color: Style.capsuleBorderColor
    border.width: Style.capsuleBorderWidth

    RowLayout {
      id: mainRow
      anchors.centerIn: parent
      spacing: Style.marginS

      Rectangle {
        width: root.dotSize
        height: root.dotSize
        radius: width / 2
        color: root.accent

        Behavior on color {
          ColorAnimation { duration: Style.animationNormal; easing.type: Easing.OutCubic }
        }
      }

      NText {
        text: root.labelText
        pointSize: root.barFontSize
        font.weight: Style.fontWeightBold
        color: Color.mOnSurface
      }

      NText {
        visible: !root.isVertical && root.txItems.length === 0 && root.secondaryText !== ""
        text: root.secondaryText
        font.family: Settings.data.ui.fontFixed
        pointSize: root.barFontSize * 0.92
        color: root.accent
      }

      RowLayout {
        visible: !root.isVertical && root.txItems.length > 0
        spacing: Math.max(4, Math.round(Style.marginXS * 0.85))

        Repeater {
          model: root.txItems

          delegate: RowLayout {
            required property var modelData
            readonly property color txAccent: TxTheme.accentColorForTx(modelData.id)
            spacing: Math.max(3, Math.round(Style.marginXS * 0.75))

            Rectangle {
              width: Math.max(6, Math.round(root.dotSize * 0.75))
              height: width
              radius: width / 2
              color: txAccent
            }

            NText {
              text: modelData.valueText
              font.family: Settings.data.ui.fontFixed
              pointSize: root.barFontSize * 0.92
              color: txAccent
              font.weight: Style.fontWeightBold
            }
          }
        }
      }
    }
  }

  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.LeftButton | Qt.MiddleButton

    onClicked: function(mouse) {
      if (mouse.button === Qt.LeftButton && pluginApi)
        pluginApi.togglePanel(screen, root);
      if (mouse.button === Qt.MiddleButton && mainInstance)
        mainInstance.refreshState();
    }

    onEntered: {
      if (mainInstance)
        TooltipService.show(root, mainInstance.tooltipText(), BarService.getTooltipDirection());
    }

    onExited: {
      TooltipService.hide();
    }
  }
}
