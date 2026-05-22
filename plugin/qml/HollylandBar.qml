import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Widgets
import "TxTheme.js" as TxTheme

Item {
  id: root

  property string labelText: "HL"
  property string secondaryText: ""
  property color accent: Color.mOnSurfaceVariant
  property var txItems: []
  property bool isVertical: false
  property real capsuleHeight: Style.baseWidgetSize
  property real barFontSize: Style.fontSizeS
  readonly property real dotSize: Math.max(8, Style.toOdd(capsuleHeight * 0.22))

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
}
